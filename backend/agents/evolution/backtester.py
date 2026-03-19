"""
backend/agents/evolution/backtester.py
準確率回測官（Opus 撰寫）

流程：
1. 查 predictions 表，找 is_verified=FALSE 且 verify_date <= TODAY
2. 從 Yahoo Finance 或 TWSE 抓取 verify_date 當天收盤價
3. 計算 actual_direction（vs prediction_date 收盤價）
4. 計算 direction_correct（vs predicted_direction）
5. 計算 score（方向正確 0.6 + 目標價命中 0.4）
6. 寫入 outcomes 表
7. 更新 predictions.is_verified = TRUE
"""

import logging
import time
from datetime import date, datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

_AGENT_DISPLAY = "Backtester"


class Backtester:
    """
    準確率回測官。

    每週由 CEOAgent.weekly_backtest() 觸發，
    驗證到期的預測並寫入 outcomes 表。
    """

    def run(self) -> dict:
        """
        主入口：驗證所有到期未驗證的預測。

        Returns:
            dict: {verified: int, skipped: int, errors: int}
        """
        from backend.data.storage.supabase_client import get_client

        client = get_client()
        if not client:
            logger.error(f"[{_AGENT_DISPLAY}] Supabase 不可用，跳過回測")
            return {"verified": 0, "skipped": 0, "errors": 0}

        today_str = date.today().isoformat()
        stats = {"verified": 0, "skipped": 0, "errors": 0}

        try:
            result = (
                client.table("predictions")
                .select("*")
                .eq("is_verified", False)
                .lte("verify_date", today_str)
                .execute()
            )
            pending = result.data or []
        except Exception as e:
            logger.error(f"[{_AGENT_DISPLAY}] 查詢 predictions 失敗: {e}")
            return stats

        logger.info(f"[{_AGENT_DISPLAY}] 找到 {len(pending)} 筆待驗證預測")

        for pred in pending:
            try:
                success = self._verify_one(client, pred)
                if success:
                    stats["verified"] += 1
                else:
                    stats["skipped"] += 1
            except Exception as e:
                logger.error(
                    f"[{_AGENT_DISPLAY}] 驗證 prediction {pred.get('id')} 失敗: {e}"
                )
                stats["errors"] += 1
            time.sleep(0.5)  # 避免 API 過度呼叫

        logger.info(
            f"[{_AGENT_DISPLAY}] 回測完成 — "
            f"驗證:{stats['verified']} 跳過:{stats['skipped']} 錯誤:{stats['errors']}"
        )
        return stats

    # ─────────────────────────────────────────────────────────
    # 內部邏輯
    # ─────────────────────────────────────────────────────────

    def _verify_one(self, client, pred: dict) -> bool:
        """
        驗證單筆預測：
        1. 抓收盤價（prediction_date + verify_date）
        2. 計算方向 & 得分
        3. 寫 outcomes + 更新 predictions
        """
        symbol        = pred["symbol"]
        market        = pred["market"]
        pred_dir      = pred["predicted_direction"]
        pred_low      = pred.get("predicted_target_low")
        pred_high     = pred.get("predicted_target_high")
        prediction_date = pred["prediction_date"]  # "YYYY-MM-DD"
        verify_date     = pred["verify_date"]       # "YYYY-MM-DD"
        pred_id         = pred["id"]

        # 1. 取兩個日期的收盤價
        price_at_pred   = self._get_close_price(symbol, market, prediction_date)
        price_at_verify = self._get_close_price(symbol, market, verify_date)

        if price_at_pred is None or price_at_verify is None:
            logger.warning(
                f"[{_AGENT_DISPLAY}] {symbol} 無法取得收盤價 "
                f"(pred={price_at_pred}, verify={price_at_verify})，跳過"
            )
            return False

        # 2. 計算實際方向
        change_pct = (price_at_verify - price_at_pred) / price_at_pred * 100
        actual_dir = self._classify_direction(change_pct)

        # 3. 判斷方向是否正確
        direction_correct = self._is_direction_correct(pred_dir, actual_dir)

        # 4. 判斷目標價是否命中
        target_hit = self._is_target_hit(
            price_at_pred, price_at_verify, pred_low, pred_high
        )

        # 5. 計算得分（方向 0.6 + 目標價 0.4）
        score = self._compute_score(direction_correct, target_hit)

        # 6. 寫入 outcomes 表
        outcome_row = {
            "prediction_id":           pred_id,
            "symbol":                  symbol,
            "actual_price_at_prediction": price_at_pred,
            "actual_price_at_verify":     price_at_verify,
            "actual_direction":           actual_dir,
            "actual_change_pct":          round(change_pct, 4),
            "direction_correct":          direction_correct,
            "target_hit":                 target_hit,
            "score":                      score,
        }
        try:
            client.table("outcomes").insert(outcome_row).execute()
        except Exception as e:
            logger.error(f"[{_AGENT_DISPLAY}] 寫入 outcomes 失敗: {e}")
            return False

        # 7. 更新 predictions.is_verified = TRUE
        try:
            client.table("predictions").update(
                {
                    "is_verified": True,
                    "verified_at": datetime.now(timezone.utc).isoformat(),
                }
            ).eq("id", pred_id).execute()
        except Exception as e:
            logger.error(f"[{_AGENT_DISPLAY}] 更新 predictions 失敗: {e}")
            # outcomes 已寫入，不視為完全失敗

        logger.info(
            f"[{_AGENT_DISPLAY}] {symbol} {verify_date} | "
            f"pred={pred_dir} actual={actual_dir} "
            f"correct={direction_correct} score={score:.2f}"
        )
        return True

    # ─────────────────────────────────────────────────────────
    # 收盤價抓取
    # ─────────────────────────────────────────────────────────

    def _get_close_price(
        self, symbol: str, market: str, date_str: str
    ) -> Optional[float]:
        """
        取得指定日期的收盤價。
        優先嘗試 Yahoo Finance，台股失敗則 fallback 到 TWSE。
        """
        # 嘗試 Yahoo Finance
        price = self._fetch_yahoo(symbol, market, date_str)
        if price is not None:
            return price

        # 台股 fallback：TWSE
        if market == "TW":
            price = self._fetch_twse(symbol, date_str)
            if price is not None:
                return price

        return None

    def _fetch_yahoo(
        self, symbol: str, market: str, date_str: str
    ) -> Optional[float]:
        """透過 yfinance 取得單日收盤價。"""
        try:
            import yfinance as yf
            from datetime import timedelta

            # Yahoo 需要加後綴
            ticker_symbol = symbol
            if market == "TW":
                ticker_symbol = f"{symbol}.TW"
            elif market == "TWO":
                ticker_symbol = f"{symbol}.TWO"

            target_date  = date.fromisoformat(date_str)
            start        = target_date.isoformat()
            end          = (target_date + timedelta(days=4)).isoformat()  # 抓幾天以防假日

            ticker = yf.Ticker(ticker_symbol)
            hist   = ticker.history(start=start, end=end, auto_adjust=True)

            if hist.empty:
                return None

            # 找最靠近 target_date 的那筆（可能是下一個交易日）
            hist.index = hist.index.date
            for d in [target_date + __import__("datetime").timedelta(days=i) for i in range(5)]:
                if d in hist.index:
                    return float(hist.loc[d, "Close"])

            return None
        except Exception as e:
            logger.debug(f"[{_AGENT_DISPLAY}] Yahoo fetch 失敗 {symbol}: {e}")
            return None

    def _fetch_twse(self, symbol: str, date_str: str) -> Optional[float]:
        """
        從 TWSE 公開 API 取得台股收盤價。
        URL: https://www.twse.com.tw/exchangeReport/STOCK_DAY?response=json&date=YYYYMMDD&stockNo=XXXX
        """
        try:
            import requests
            date_nodash = date_str.replace("-", "")
            url = (
                f"https://www.twse.com.tw/exchangeReport/STOCK_DAY"
                f"?response=json&date={date_nodash}&stockNo={symbol}"
            )
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            data = resp.json()

            target = date.fromisoformat(date_str)
            # TWSE 日期格式：民國年/月/日，例如 "113/03/01"
            roc_year = target.year - 1911
            target_roc = f"{roc_year}/{target.month:02d}/{target.day:02d}"

            for row in data.get("data", []):
                if row[0] == target_roc:
                    close_str = row[6].replace(",", "")
                    return float(close_str)

            return None
        except Exception as e:
            logger.debug(f"[{_AGENT_DISPLAY}] TWSE fetch 失敗 {symbol}: {e}")
            return None

    # ─────────────────────────────────────────────────────────
    # 計算邏輯
    # ─────────────────────────────────────────────────────────

    def _classify_direction(self, change_pct: float) -> str:
        """
        依漲跌幅分類實際方向。
        > +1.5% → bullish, < -1.5% → bearish, 否則 → neutral
        """
        if change_pct > 1.5:
            return "bullish"
        elif change_pct < -1.5:
            return "bearish"
        else:
            return "neutral"

    def _is_direction_correct(self, predicted: str, actual: str) -> bool:
        """
        判斷方向是否正確。
        cautious_bullish / bullish 都算 bullish 方向；
        cautious_bearish / bearish 都算 bearish 方向。
        """
        def normalize(d: str) -> str:
            if "bullish" in d:
                return "bullish"
            elif "bearish" in d:
                return "bearish"
            return "neutral"

        return normalize(predicted) == normalize(actual)

    def _is_target_hit(
        self,
        price_pred:   float,
        price_verify: float,
        pred_low:     Optional[float],
        pred_high:    Optional[float],
    ) -> Optional[bool]:
        """
        判斷目標價是否命中（驗證日收盤價落在預測區間內）。
        若未提供目標價，回傳 None。
        """
        if pred_low is None or pred_high is None:
            return None

        low  = min(pred_low, pred_high)
        high = max(pred_low, pred_high)

        # 允許 ±2% 容忍區間
        tolerance = price_pred * 0.02
        return (low - tolerance) <= price_verify <= (high + tolerance)

    def _compute_score(
        self, direction_correct: bool, target_hit: Optional[bool]
    ) -> float:
        """
        score = 方向正確 × 0.6 + 目標價命中 × 0.4
        目標價未提供時，score 最高為 0.6。
        """
        score = 0.6 if direction_correct else 0.0
        if target_hit is True:
            score += 0.4
        return round(score, 2)


# ─────────────────────────────────────────────────────────
# 模組級單例
# ─────────────────────────────────────────────────────────

_backtester: Optional[Backtester] = None


def get_backtester() -> Backtester:
    global _backtester
    if _backtester is None:
        _backtester = Backtester()
    return _backtester
