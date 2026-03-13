"""
本地 SQLite 儲存層 — 取代即時 Supabase REST API 查詢
使用 HuggingFace persistent storage（/data）或本地 .cache 目錄
"""
import logging
import os
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

# 儲存路徑：HF free tier 用 /tmp（ephemeral），本地開發用 .cache
_LOCAL_FALLBACK = os.path.join(os.getcwd(), ".cache")


def _db_path() -> str:
    """決定 SQLite 檔案路徑：/tmp（HF）或 .cache（本地開發）"""
    # HuggingFace 環境（偵測 SPACE_ID 環境變數）
    if os.environ.get("SPACE_ID"):
        return "/tmp/discover.db"
    # 本地開發
    try:
        os.makedirs(_LOCAL_FALLBACK, exist_ok=True)
        return os.path.join(_LOCAL_FALLBACK, "discover.db")
    except Exception:
        return "/tmp/discover.db"


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

                    CREATE TABLE IF NOT EXISTS ai_predictions (
                        id TEXT PRIMARY KEY,
                        user_id TEXT DEFAULT '',
                        symbol TEXT NOT NULL,
                        predicted_at TEXT NOT NULL,
                        evaluated_at TEXT DEFAULT NULL,
                        direction TEXT NOT NULL,
                        confidence INTEGER DEFAULT 0,
                        raw_confidence INTEGER DEFAULT 0,
                        entry_price REAL DEFAULT 0,
                        target_price REAL DEFAULT 0,
                        stop_price REAL DEFAULT 0,
                        horizon_days INTEGER DEFAULT 20,
                        tier TEXT DEFAULT 'free',
                        model_name TEXT DEFAULT '',
                        analysis_type TEXT DEFAULT 'full',
                        source_route TEXT DEFAULT '',
                        prompt_version TEXT DEFAULT '',
                        rule_version TEXT DEFAULT '',
                        system_version TEXT DEFAULT '',
                        quality_pass INTEGER DEFAULT 1,
                        status TEXT DEFAULT 'open',
                        actual_return_pct REAL DEFAULT NULL,
                        evaluation_notes TEXT DEFAULT '',
                        summary_json TEXT DEFAULT '',
                        created_at TEXT DEFAULT (datetime('now')),
                        updated_at TEXT DEFAULT (datetime('now'))
                    );

                    CREATE TABLE IF NOT EXISTS ai_evaluation_runs (
                        id TEXT PRIMARY KEY,
                        run_type TEXT DEFAULT 'scheduled',
                        created_at TEXT DEFAULT (datetime('now')),
                        evaluated_count INTEGER DEFAULT 0,
                        details_json TEXT DEFAULT ''
                    );

                    CREATE TABLE IF NOT EXISTS prompt_change_log (
                        id TEXT PRIMARY KEY,
                        change_type TEXT NOT NULL DEFAULT 'prompt',
                        old_version TEXT DEFAULT '',
                        new_version TEXT DEFAULT '',
                        reason TEXT DEFAULT '',
                        expected_improvement TEXT DEFAULT '',
                        evidence TEXT DEFAULT '',
                        changed_by TEXT DEFAULT 'system',
                        created_at TEXT DEFAULT (datetime('now'))
                    );

                    CREATE INDEX IF NOT EXISTS idx_ai_usage_user_date ON ai_usage(user_id, date);
                    CREATE INDEX IF NOT EXISTS idx_watchlist_user ON watchlist(user_id);
                    CREATE INDEX IF NOT EXISTS idx_portfolios_user ON portfolios(user_id);
                    CREATE INDEX IF NOT EXISTS idx_ai_predictions_status_predicted ON ai_predictions(status, predicted_at);
                    CREATE INDEX IF NOT EXISTS idx_ai_predictions_symbol_predicted ON ai_predictions(symbol, predicted_at);
                    CREATE INDEX IF NOT EXISTS idx_ai_predictions_versions ON ai_predictions(prompt_version, rule_version, system_version);
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

    # ────────────────────── AI Predictions ──────────────────────

    def save_ai_prediction(self, record: Dict[str, Any]) -> bool:
        """儲存 AI 建議與追蹤 metadata。"""
        prediction_id = str(record.get("id") or "").strip()
        symbol = str(record.get("symbol") or "").strip().upper()
        predicted_at = str(record.get("predicted_at") or "").strip()
        direction = str(record.get("direction") or "").strip().lower()
        if not prediction_id or not symbol or not predicted_at or not direction:
            return False

        with self._lock:
            conn = self._conn()
            try:
                conn.execute("""
                    INSERT INTO ai_predictions (
                        id, user_id, symbol, predicted_at, evaluated_at, direction,
                        confidence, raw_confidence, entry_price, target_price, stop_price,
                        horizon_days, tier, model_name, analysis_type, source_route,
                        prompt_version, rule_version, system_version, quality_pass,
                        status, actual_return_pct, evaluation_notes, summary_json,
                        created_at, updated_at
                    ) VALUES (
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                        datetime('now'), datetime('now')
                    )
                    ON CONFLICT(id) DO UPDATE SET
                        user_id = excluded.user_id,
                        symbol = excluded.symbol,
                        predicted_at = excluded.predicted_at,
                        evaluated_at = excluded.evaluated_at,
                        direction = excluded.direction,
                        confidence = excluded.confidence,
                        raw_confidence = excluded.raw_confidence,
                        entry_price = excluded.entry_price,
                        target_price = excluded.target_price,
                        stop_price = excluded.stop_price,
                        horizon_days = excluded.horizon_days,
                        tier = excluded.tier,
                        model_name = excluded.model_name,
                        analysis_type = excluded.analysis_type,
                        source_route = excluded.source_route,
                        prompt_version = excluded.prompt_version,
                        rule_version = excluded.rule_version,
                        system_version = excluded.system_version,
                        quality_pass = excluded.quality_pass,
                        status = excluded.status,
                        actual_return_pct = excluded.actual_return_pct,
                        evaluation_notes = excluded.evaluation_notes,
                        summary_json = excluded.summary_json,
                        updated_at = datetime('now')
                """, (
                    prediction_id,
                    str(record.get("user_id") or "").strip(),
                    symbol,
                    predicted_at,
                    record.get("evaluated_at"),
                    direction,
                    int(record.get("confidence") or 0),
                    int(record.get("raw_confidence") or 0),
                    float(record.get("entry_price") or 0),
                    float(record.get("target_price") or 0),
                    float(record.get("stop_price") or 0),
                    int(record.get("horizon_days") or 20),
                    str(record.get("tier") or "free").strip().lower(),
                    str(record.get("model_name") or "").strip(),
                    str(record.get("analysis_type") or "full").strip(),
                    str(record.get("source_route") or "").strip(),
                    str(record.get("prompt_version") or "").strip(),
                    str(record.get("rule_version") or "").strip(),
                    str(record.get("system_version") or "").strip(),
                    1 if bool(record.get("quality_pass", True)) else 0,
                    str(record.get("status") or "open").strip().lower(),
                    record.get("actual_return_pct"),
                    str(record.get("evaluation_notes") or "").strip(),
                    str(record.get("summary_json") or "").strip(),
                ))
                conn.commit()
                return True
            except Exception as e:
                logger.warning("[LocalStore] save_ai_prediction 失敗: %s", e)
                return False
            finally:
                conn.close()

    def update_ai_prediction(self, prediction_id: str, updates: Dict[str, Any]) -> bool:
        prediction_id = str(prediction_id or "").strip()
        if not prediction_id or not isinstance(updates, dict):
            return False

        allowed = {
            "evaluated_at",
            "confidence",
            "raw_confidence",
            "target_price",
            "stop_price",
            "status",
            "actual_return_pct",
            "evaluation_notes",
            "prompt_version",
            "rule_version",
            "system_version",
            "summary_json",
        }
        payload = {k: v for k, v in updates.items() if k in allowed}
        if not payload:
            return False

        assignments = ", ".join(f"{k} = ?" for k in payload.keys())
        values = list(payload.values())
        values.extend([prediction_id])

        with self._lock:
            conn = self._conn()
            try:
                conn.execute(
                    f"UPDATE ai_predictions SET {assignments}, updated_at = datetime('now') WHERE id = ?",
                    values,
                )
                conn.commit()
                return True
            except Exception as e:
                logger.warning("[LocalStore] update_ai_prediction 失敗: %s", e)
                return False
            finally:
                conn.close()

    def list_ai_predictions(
        self,
        *,
        status: Optional[str] = None,
        exclude_status: Optional[str] = None,
        predicted_since: Optional[str] = None,
        predicted_before: Optional[str] = None,
        evaluated_since: Optional[str] = None,
        limit: int = 5000,
    ) -> List[Dict[str, Any]]:
        clauses: List[str] = []
        params: List[Any] = []
        if status:
            clauses.append("status = ?")
            params.append(status)
        if exclude_status:
            clauses.append("status != ?")
            params.append(exclude_status)
        if predicted_since:
            clauses.append("predicted_at >= ?")
            params.append(predicted_since)
        if predicted_before:
            clauses.append("predicted_at < ?")
            params.append(predicted_before)
        if evaluated_since:
            clauses.append("evaluated_at >= ?")
            params.append(evaluated_since)

        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        safe_limit = max(1, min(int(limit or 5000), 10000))

        conn = self._conn()
        try:
            rows = conn.execute(
                f"""
                SELECT *
                FROM ai_predictions
                {where_sql}
                ORDER BY predicted_at DESC
                LIMIT ?
                """,
                (*params, safe_limit),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def add_ai_evaluation_run(self, run_id: str, run_type: str, evaluated_count: int, details_json: str) -> bool:
        run_id = str(run_id or "").strip()
        if not run_id:
            return False
        with self._lock:
            conn = self._conn()
            try:
                conn.execute("""
                    INSERT INTO ai_evaluation_runs (id, run_type, evaluated_count, details_json, created_at)
                    VALUES (?, ?, ?, ?, datetime('now'))
                """, (run_id, str(run_type or "scheduled"), int(evaluated_count or 0), str(details_json or "")))
                conn.commit()
                return True
            except Exception as e:
                logger.warning("[LocalStore] add_ai_evaluation_run 失敗: %s", e)
                return False
            finally:
                conn.close()

    # ────────────────────── Prompt / Rule Change Log ──────────────────────

    def add_prompt_change(self, record: Dict[str, Any]) -> bool:
        change_id = str(record.get("id") or "").strip()
        if not change_id:
            return False
        with self._lock:
            conn = self._conn()
            try:
                conn.execute("""
                    INSERT INTO prompt_change_log (
                        id, change_type, old_version, new_version,
                        reason, expected_improvement, evidence, changed_by, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                    ON CONFLICT(id) DO NOTHING
                """, (
                    change_id,
                    str(record.get("change_type") or "prompt").strip(),
                    str(record.get("old_version") or "").strip(),
                    str(record.get("new_version") or "").strip(),
                    str(record.get("reason") or "").strip(),
                    str(record.get("expected_improvement") or "").strip(),
                    str(record.get("evidence") or "").strip(),
                    str(record.get("changed_by") or "system").strip(),
                ))
                conn.commit()
                return True
            except Exception as e:
                logger.warning("[LocalStore] add_prompt_change failed: %s", e)
                return False
            finally:
                conn.close()

    def list_prompt_changes(self, limit: int = 200) -> List[Dict[str, Any]]:
        conn = self._conn()
        try:
            rows = conn.execute(
                "SELECT * FROM prompt_change_log ORDER BY created_at DESC LIMIT ?",
                (max(1, min(int(limit), 1000)),),
            ).fetchall()
            return [dict(r) for r in rows]
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
            for table in ("users", "user_subscriptions", "ai_usage", "watchlist", "portfolios", "ai_predictions", "ai_evaluation_runs", "prompt_change_log"):
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
            for table in ("users", "user_subscriptions", "ai_usage", "watchlist", "portfolios", "ai_predictions", "ai_evaluation_runs", "prompt_change_log"):
                row = conn.execute(f"SELECT COUNT(*) as cnt FROM {table}").fetchone()
                stats[table] = row["cnt"] if row else 0
            return stats
        finally:
            conn.close()


# 單例
local_store = LocalStore()
