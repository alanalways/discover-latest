"""
backend/agents/evolution/backtester.py

回測尚未驗證的 predictions，並寫入 outcomes。
"""

import logging
import time
from datetime import date, datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger(__name__)

_AGENT_DISPLAY = "Backtester"


class Backtester:
    """每週驗證到期 prediction。"""

    def run(self) -> dict:
        from backend.data.storage.supabase_client import get_client

        client = get_client()
        if not client:
            logger.error("[%s] Supabase unavailable", _AGENT_DISPLAY)
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
        except Exception as exc:
            logger.error("[%s] failed to load predictions: %s", _AGENT_DISPLAY, exc)
            return stats

        logger.info("[%s] %s predictions pending verification", _AGENT_DISPLAY, len(pending))

        for prediction in pending:
            try:
                if self._verify_one(client, prediction):
                    stats["verified"] += 1
                else:
                    stats["skipped"] += 1
            except Exception as exc:
                logger.error(
                    "[%s] verify prediction %s failed: %s",
                    _AGENT_DISPLAY,
                    prediction.get("id"),
                    exc,
                )
                stats["errors"] += 1
            time.sleep(0.25)

        logger.info("[%s] done: %s", _AGENT_DISPLAY, stats)
        return stats

    def _verify_one(self, client, prediction: dict) -> bool:
        symbol = prediction["symbol"]
        market = prediction["market"]
        predicted_direction = prediction["predicted_direction"]
        prediction_date = prediction["prediction_date"]
        verify_date = prediction["verify_date"]

        price_at_prediction = self._get_close_price(symbol, market, prediction_date)
        price_at_verify = self._get_close_price(symbol, market, verify_date)

        if price_at_prediction is None or price_at_verify is None:
            logger.warning(
                "[%s] skip %s, missing price pred=%s verify=%s",
                _AGENT_DISPLAY,
                symbol,
                price_at_prediction,
                price_at_verify,
            )
            return False

        change_pct = (price_at_verify - price_at_prediction) / price_at_prediction * 100
        actual_direction = self._classify_direction(change_pct)
        direction_correct = self._is_direction_correct(predicted_direction, actual_direction)
        target_hit = self._is_target_hit(
            price_at_prediction,
            price_at_verify,
            prediction.get("predicted_target_low"),
            prediction.get("predicted_target_high"),
        )
        score = self._compute_score(direction_correct, target_hit)

        outcome_row = {
            "prediction_id": prediction["id"],
            "symbol": symbol,
            "actual_price_at_prediction": price_at_prediction,
            "actual_price_at_verify": price_at_verify,
            "actual_direction": actual_direction,
            "actual_change_pct": round(change_pct, 4),
            "direction_correct": direction_correct,
            "target_hit": target_hit,
            "score": score,
        }

        try:
            client.table("outcomes").insert(outcome_row).execute()
            client.table("predictions").update(
                {
                    "is_verified": True,
                    "verified_at": datetime.now(timezone.utc).isoformat(),
                }
            ).eq("id", prediction["id"]).execute()
        except Exception as exc:
            logger.error("[%s] failed to persist outcome: %s", _AGENT_DISPLAY, exc)
            return False

        logger.info(
            "[%s] %s verified: pred=%s actual=%s score=%.2f",
            _AGENT_DISPLAY,
            symbol,
            predicted_direction,
            actual_direction,
            score,
        )
        return True

    def _get_close_price(self, symbol: str, market: str, date_str: str) -> Optional[float]:
        if market in ("TW", "TWO"):
            price = self._fetch_finmind(symbol, date_str)
            if price is not None:
                return price

        price = self._fetch_yahoo(symbol, market, date_str)
        if price is not None:
            return price

        if market in ("TW", "TWO"):
            price = self._fetch_twse(symbol, date_str)
            if price is not None:
                return price

        return None

    def _fetch_finmind(self, symbol: str, date_str: str) -> Optional[float]:
        """
        依 target date 精準回抓 FinMind 歷史資料。

        不再固定抓最近 10 天，改為以 target 與今天的距離決定回抓範圍，
        避免 prediction_date/verify_date 拿到近期錯誤基準價。
        """
        try:
            from backend.data.sources.finmind import get_price_data

            target_date = date.fromisoformat(date_str)
            days_needed = max(30, (date.today() - target_date).days + 10)
            data = get_price_data(symbol, days=days_needed)
            dates = data.get("dates") or []
            closes = data.get("closes") or []
            if not dates or not closes:
                return None

            for idx, current_date in enumerate(dates):
                if current_date >= date_str:
                    return float(closes[idx])
            return None
        except Exception as exc:
            logger.debug("[%s] FinMind fetch failed for %s: %s", _AGENT_DISPLAY, symbol, exc)
            return None

    def _fetch_yahoo(self, symbol: str, market: str, date_str: str) -> Optional[float]:
        try:
            import yfinance as yf

            ticker_symbol = symbol
            if market == "TW":
                ticker_symbol = f"{symbol}.TW"
            elif market == "TWO":
                ticker_symbol = f"{symbol}.TWO"

            target_date = date.fromisoformat(date_str)
            ticker = yf.Ticker(ticker_symbol)
            hist = ticker.history(
                start=target_date.isoformat(),
                end=(target_date + timedelta(days=5)).isoformat(),
                auto_adjust=True,
            )
            if hist.empty:
                return None

            hist.index = hist.index.date
            for offset in range(5):
                current = target_date + timedelta(days=offset)
                if current in hist.index:
                    return float(hist.loc[current, "Close"])
            return None
        except Exception as exc:
            logger.debug("[%s] Yahoo fetch failed for %s: %s", _AGENT_DISPLAY, symbol, exc)
            return None

    def _fetch_twse(self, symbol: str, date_str: str) -> Optional[float]:
        try:
            import requests

            target = date.fromisoformat(date_str)
            month_start = target.replace(day=1)
            url = (
                "https://www.twse.com.tw/exchangeReport/STOCK_DAY"
                f"?response=json&date={month_start.strftime('%Y%m%d')}&stockNo={symbol}"
            )
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            data = resp.json()

            roc_year = target.year - 1911
            target_roc = f"{roc_year}/{target.month:02d}/{target.day:02d}"

            for row in data.get("data", []):
                if row[0] == target_roc:
                    return float(row[6].replace(",", ""))
            return None
        except Exception as exc:
            logger.debug("[%s] TWSE fetch failed for %s: %s", _AGENT_DISPLAY, symbol, exc)
            return None

    def _classify_direction(self, change_pct: float) -> str:
        if change_pct > 1.5:
            return "bullish"
        if change_pct < -1.5:
            return "bearish"
        return "neutral"

    def _is_direction_correct(self, predicted: str, actual: str) -> bool:
        def normalize(direction: str) -> str:
            direction = str(direction or "").strip().lower()
            if direction in {"up", "long"}:
                return "bullish"
            if direction in {"down", "short"}:
                return "bearish"
            if "bullish" in direction:
                return "bullish"
            if "bearish" in direction:
                return "bearish"
            return "neutral"

        return normalize(predicted) == normalize(actual)

    def _is_target_hit(
        self,
        price_at_prediction: float,
        price_at_verify: float,
        target_low: Optional[float],
        target_high: Optional[float],
    ) -> Optional[bool]:
        if target_low is None or target_high is None:
            return None

        low = min(target_low, target_high)
        high = max(target_low, target_high)
        tolerance = price_at_prediction * 0.02
        return (low - tolerance) <= price_at_verify <= (high + tolerance)

    def _compute_score(self, direction_correct: bool, target_hit: Optional[bool]) -> float:
        score = 0.6 if direction_correct else 0.0
        if target_hit is True:
            score += 0.4
        return round(score, 2)


_backtester: Optional[Backtester] = None


def get_backtester() -> Backtester:
    global _backtester
    if _backtester is None:
        _backtester = Backtester()
    return _backtester
