"""
本地 SQLite 儲存層 — 取代即時 Supabase REST API 查詢
使用 HuggingFace persistent storage（/data）或本地 .cache 目錄
"""
import json
import logging
import os
import sqlite3
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

# HuggingFace Spaces 持久化路徑
_HF_DATA_DIR = "/data"
_LOCAL_FALLBACK = os.path.join(os.getcwd(), ".cache")


def _db_path() -> str:
    """決定 SQLite 檔案路徑"""
    if os.path.isdir(_HF_DATA_DIR) and os.access(_HF_DATA_DIR, os.W_OK):
        return os.path.join(_HF_DATA_DIR, "discover.db")
    os.makedirs(_LOCAL_FALLBACK, exist_ok=True)
    return os.path.join(_LOCAL_FALLBACK, "discover.db")


class LocalStore:
    """Thread-safe SQLite 本地儲存"""

    def __init__(self):
        self._db_file = _db_path()
        self._lock = threading.Lock()
        self._init_db()
        logger.info("[LocalStore] 初始化完成: %s", self._db_file)

    # ────────────────────── 初始化 ──────────────────────

    def _conn(self) -> sqlite3.Connection:
        """取得連線（每次新建，SQLite 本身有 file-level locking）"""
        conn = sqlite3.connect(self._db_file, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=OFF")
        return conn

    def _init_db(self):
        """建立必要的表"""
        with self._lock:
            conn = self._conn()
            try:
                conn.executescript("""
                    CREATE TABLE IF NOT EXISTS users (
                        id TEXT PRIMARY KEY,
                        email TEXT DEFAULT '',
                        name TEXT DEFAULT '',
                        tier TEXT DEFAULT 'free',
                        created_at TEXT DEFAULT '',
                        last_sign_in_at TEXT DEFAULT '',
                        updated_at TEXT DEFAULT (datetime('now'))
                    );

                    CREATE TABLE IF NOT EXISTS user_subscriptions (
                        user_id TEXT PRIMARY KEY,
                        tier TEXT DEFAULT 'free',
                        expires_at TEXT DEFAULT NULL,
                        updated_at TEXT DEFAULT (datetime('now'))
                    );

                    CREATE TABLE IF NOT EXISTS ai_usage (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id TEXT NOT NULL,
                        date TEXT NOT NULL,
                        count INTEGER DEFAULT 1,
                        updated_at TEXT DEFAULT (datetime('now')),
                        UNIQUE(user_id, date)
                    );

                    CREATE TABLE IF NOT EXISTS watchlist (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id TEXT NOT NULL,
                        symbol TEXT NOT NULL,
                        name TEXT DEFAULT '',
                        added_at TEXT DEFAULT (datetime('now')),
                        UNIQUE(user_id, symbol)
                    );

                    CREATE TABLE IF NOT EXISTS portfolios (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id TEXT NOT NULL,
                        symbol TEXT NOT NULL,
                        shares INTEGER DEFAULT 0,
                        avg_price REAL DEFAULT 0,
                        updated_at TEXT DEFAULT (datetime('now')),
                        UNIQUE(user_id, symbol)
                    );

                    CREATE INDEX IF NOT EXISTS idx_ai_usage_user_date ON ai_usage(user_id, date);
                    CREATE INDEX IF NOT EXISTS idx_watchlist_user ON watchlist(user_id);
                    CREATE INDEX IF NOT EXISTS idx_portfolios_user ON portfolios(user_id);
                """)
                conn.commit()
            finally:
                conn.close()

    # ────────────────────── Users ──────────────────────

    def upsert_user(self, user_id: str, email: str = "", name: str = "",
                    tier: str = "free", created_at: str = "",
                    last_sign_in_at: str = "") -> bool:
        with self._lock:
            conn = self._conn()
            try:
                conn.execute("""
                    INSERT INTO users (id, email, name, tier, created_at, last_sign_in_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
                    ON CONFLICT(id) DO UPDATE SET
                        email = COALESCE(NULLIF(excluded.email, ''), email),
                        name = COALESCE(NULLIF(excluded.name, ''), name),
                        tier = COALESCE(NULLIF(excluded.tier, ''), tier),
                        created_at = COALESCE(NULLIF(excluded.created_at, ''), created_at),
                        last_sign_in_at = COALESCE(NULLIF(excluded.last_sign_in_at, ''), last_sign_in_at),
                        updated_at = datetime('now')
                """, (user_id, email, name, tier, created_at, last_sign_in_at))
                conn.commit()
                return True
            except Exception as e:
                logger.warning("[LocalStore] upsert_user 失敗: %s", e)
                return False
            finally:
                conn.close()

    def get_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        conn = self._conn()
        try:
            row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def get_all_users(self) -> List[Dict[str, Any]]:
        """取得所有使用者，含 AI 用量和 watchlist 數"""
        conn = self._conn()
        try:
            rows = conn.execute("""
                SELECT
                    u.id, u.email, u.name, u.tier, u.created_at, u.last_sign_in_at,
                    COALESCE(au_today.cnt, 0) AS ai_usage_today,
                    COALESCE(au_total.cnt, 0) AS ai_usage_total,
                    COALESCE(wl.cnt, 0) AS watchlist_count
                FROM users u
                LEFT JOIN (
                    SELECT user_id, SUM(count) as cnt
                    FROM ai_usage WHERE date = date('now')
                    GROUP BY user_id
                ) au_today ON u.id = au_today.user_id
                LEFT JOIN (
                    SELECT user_id, SUM(count) as cnt
                    FROM ai_usage
                    GROUP BY user_id
                ) au_total ON u.id = au_total.user_id
                LEFT JOIN (
                    SELECT user_id, COUNT(*) as cnt
                    FROM watchlist
                    GROUP BY user_id
                ) wl ON u.id = wl.user_id
                ORDER BY u.created_at DESC
            """).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    # ────────────────────── Subscriptions ──────────────────────

    def upsert_subscription(self, user_id: str, tier: str = "free",
                            expires_at: Optional[str] = None) -> bool:
        with self._lock:
            conn = self._conn()
            try:
                conn.execute("""
                    INSERT INTO user_subscriptions (user_id, tier, expires_at, updated_at)
                    VALUES (?, ?, ?, datetime('now'))
                    ON CONFLICT(user_id) DO UPDATE SET
                        tier = excluded.tier,
                        expires_at = excluded.expires_at,
                        updated_at = datetime('now')
                """, (user_id, tier, expires_at))
                conn.commit()
                return True
            except Exception as e:
                logger.warning("[LocalStore] upsert_subscription 失敗: %s", e)
                return False
            finally:
                conn.close()

    def get_subscription(self, user_id: str) -> Dict[str, Any]:
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT tier, expires_at FROM user_subscriptions WHERE user_id = ?",
                (user_id,)
            ).fetchone()
            return dict(row) if row else {"tier": "free", "expires_at": None}
        finally:
            conn.close()

    # ────────────────────── AI Usage ──────────────────────

    def _today_str(self) -> str:
        tz = os.environ.get("AI_USAGE_TIMEZONE", "Asia/Taipei")
        try:
            return datetime.now(ZoneInfo(tz)).date().isoformat()
        except Exception:
            return datetime.now(timezone.utc).date().isoformat()

    def get_ai_usage_today(self, user_id: str) -> int:
        today = self._today_str()
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT count FROM ai_usage WHERE user_id = ? AND date = ?",
                (user_id, today)
            ).fetchone()
            return row["count"] if row else 0
        finally:
            conn.close()

    def increment_ai_usage(self, user_id: str) -> int:
        today = self._today_str()
        with self._lock:
            conn = self._conn()
            try:
                conn.execute("""
                    INSERT INTO ai_usage (user_id, date, count, updated_at)
                    VALUES (?, ?, 1, datetime('now'))
                    ON CONFLICT(user_id, date) DO UPDATE SET
                        count = count + 1,
                        updated_at = datetime('now')
                """, (user_id, today))
                conn.commit()
                row = conn.execute(
                    "SELECT count FROM ai_usage WHERE user_id = ? AND date = ?",
                    (user_id, today)
                ).fetchone()
                return row["count"] if row else 1
            finally:
                conn.close()

    # ────────────────────── Watchlist ──────────────────────

    def get_watchlist(self, user_id: str) -> List[Dict[str, Any]]:
        conn = self._conn()
        try:
            rows = conn.execute(
                "SELECT symbol, name, added_at FROM watchlist WHERE user_id = ? ORDER BY added_at DESC",
                (user_id,)
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def add_to_watchlist(self, user_id: str, symbol: str, name: str = "") -> bool:
        symbol = (symbol or "").strip().upper()
        if not symbol:
            return False
        with self._lock:
            conn = self._conn()
            try:
                conn.execute("""
                    INSERT INTO watchlist (user_id, symbol, name, added_at)
                    VALUES (?, ?, ?, datetime('now'))
                    ON CONFLICT(user_id, symbol) DO UPDATE SET
                        name = COALESCE(NULLIF(excluded.name, ''), name)
                """, (user_id, symbol, name))
                conn.commit()
                return True
            except Exception as e:
                logger.warning("[LocalStore] add_to_watchlist 失敗: %s", e)
                return False
            finally:
                conn.close()

    def remove_from_watchlist(self, user_id: str, symbol: str) -> bool:
        symbol = (symbol or "").strip().upper()
        with self._lock:
            conn = self._conn()
            try:
                conn.execute(
                    "DELETE FROM watchlist WHERE user_id = ? AND symbol = ?",
                    (user_id, symbol)
                )
                conn.commit()
                return True
            except Exception:
                return False
            finally:
                conn.close()

    # ────────────────────── Portfolio ──────────────────────

    def get_portfolio(self, user_id: str) -> List[Dict[str, Any]]:
        conn = self._conn()
        try:
            rows = conn.execute(
                "SELECT symbol, shares, avg_price FROM portfolios WHERE user_id = ?",
                (user_id,)
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def save_portfolio(self, user_id: str, holdings: List[Dict[str, Any]]) -> bool:
        with self._lock:
            conn = self._conn()
            try:
                conn.execute("DELETE FROM portfolios WHERE user_id = ?", (user_id,))
                for h in holdings:
                    symbol = (h.get("symbol") or "").strip().upper()
                    if not symbol:
                        continue
                    conn.execute("""
                        INSERT INTO portfolios (user_id, symbol, shares, avg_price, updated_at)
                        VALUES (?, ?, ?, ?, datetime('now'))
                    """, (user_id, symbol, int(h.get("shares", 0)), float(h.get("avg_price", 0))))
                conn.commit()
                return True
            except Exception as e:
                logger.warning("[LocalStore] save_portfolio 失敗: %s", e)
                return False
            finally:
                conn.close()

    # ────────────────────── 匯入/匯出（同步用）──────────────────────

    def import_users(self, users: List[Dict[str, Any]]) -> int:
        """批次匯入使用者（from Supabase）"""
        count = 0
        for u in users:
            uid = u.get("id") or ""
            if not uid:
                continue
            self.upsert_user(
                user_id=uid,
                email=u.get("email", ""),
                name=u.get("name", ""),
                tier=u.get("tier", "free"),
                created_at=u.get("created_at", ""),
                last_sign_in_at=u.get("last_sign_in_at", ""),
            )
            count += 1
        logger.info("[LocalStore] 匯入 %d 筆使用者", count)
        return count

    def import_ai_usage(self, rows: List[Dict[str, Any]]) -> int:
        """批次匯入 AI 用量"""
        count = 0
        with self._lock:
            conn = self._conn()
            try:
                for r in rows:
                    uid = str(r.get("user_id") or "").strip()
                    date = str(r.get("date") or "").strip()
                    cnt = int(r.get("count") or 0)
                    if not uid or not date:
                        continue
                    conn.execute("""
                        INSERT INTO ai_usage (user_id, date, count, updated_at)
                        VALUES (?, ?, ?, datetime('now'))
                        ON CONFLICT(user_id, date) DO UPDATE SET
                            count = MAX(count, excluded.count),
                            updated_at = datetime('now')
                    """, (uid, date, cnt))
                    count += 1
                conn.commit()
            finally:
                conn.close()
        logger.info("[LocalStore] 匯入 %d 筆 AI 用量", count)
        return count

    def export_all(self) -> Dict[str, List[Dict[str, Any]]]:
        """匯出所有資料用於備份"""
        conn = self._conn()
        try:
            result = {}
            for table in ("users", "user_subscriptions", "ai_usage", "watchlist", "portfolios"):
                rows = conn.execute(f"SELECT * FROM {table}").fetchall()
                result[table] = [dict(r) for r in rows]
            return result
        finally:
            conn.close()

    def is_empty(self) -> bool:
        """檢查是否為空資料庫（首次啟動判斷）"""
        conn = self._conn()
        try:
            row = conn.execute("SELECT COUNT(*) as cnt FROM users").fetchone()
            return (row["cnt"] if row else 0) == 0
        finally:
            conn.close()

    def get_stats(self) -> Dict[str, int]:
        """取得各表記錄數"""
        conn = self._conn()
        try:
            stats = {}
            for table in ("users", "user_subscriptions", "ai_usage", "watchlist", "portfolios"):
                row = conn.execute(f"SELECT COUNT(*) as cnt FROM {table}").fetchone()
                stats[table] = row["cnt"] if row else 0
            return stats
        finally:
            conn.close()


# 單例
local_store = LocalStore()
