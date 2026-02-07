"""
Price Prediction Service - 價格預測服務
提供 Naive / ARIMA / Prophet 三種 baseline 模型
含 walk-forward 驗證、快取、配額管理
"""
import math
import hashlib
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
from collections import OrderedDict


# 記憶體快取 (LRU 風格)
_prediction_cache: OrderedDict = OrderedDict()
_CACHE_MAX = 200


def _cache_key(symbol: str, model: str, horizon: int) -> str:
    today = datetime.now().strftime("%Y-%m-%d")
    return hashlib.md5(f"{symbol}:{model}:{horizon}:{today}".encode()).hexdigest()


class PredictionService:
    """價格預測服務"""

    MODELS = {
        "naive": "Naive (持平/漂移)",
        "arima": "ARIMA",
        "prophet": "Prophet",
    }

    HORIZONS = {5: "5 日", 20: "20 日", 60: "60 日"}

    DISCLAIMER = (
        "⚠️ 價格預測為統計/時間序列推估結果，不保證準確，非投資建議。"
        "過去表現不代表未來績效，投資有虧損風險。"
    )

    def predict(
        self,
        history: List[Dict],
        model: str = "naive",
        horizon: int = 20,
        confidence: float = 0.80,
    ) -> Dict[str, Any]:
        """
        執行價格預測

        Args:
            history: 歷史日K資料 (需含 date, close)
            model: 模型 (naive / arima / prophet)
            horizon: 預測天數
            confidence: 信賴區間 (0.80 = 80%)

        Returns:
            預測結果含預測值、上下界、誤差指標
        """
        if not history or len(history) < 60:
            return {"error": "歷史資料不足（至少需要 60 日）"}

        # 檢查快取
        symbol = history[-1].get("symbol", "UNKNOWN")
        ck = _cache_key(symbol, model, horizon)
        if ck in _prediction_cache:
            return _prediction_cache[ck]

        prices = [float(h.get("close", 0)) for h in history if h.get("close")]
        dates = [h.get("date", "") for h in history if h.get("close")]

        if len(prices) < 60:
            return {"error": "有效價格資料不足"}

        # 執行預測
        if model == "naive":
            forecast = self._naive_predict(prices, horizon)
        elif model == "arima":
            forecast = self._arima_predict(prices, horizon)
        elif model == "prophet":
            forecast = self._prophet_predict(prices, dates, horizon)
        else:
            return {"error": f"不支援的模型: {model}"}

        # Walk-forward 驗證
        metrics = self._walk_forward_validate(prices, model, horizon)

        # 計算信賴區間
        std_dev = metrics.get("rmse", 0)
        z_score = 1.28 if confidence == 0.80 else 1.96  # 80% or 95%

        upper_band = [p + z_score * std_dev for p in forecast["values"]]
        lower_band = [max(0, p - z_score * std_dev) for p in forecast["values"]]

        # 產生預測日期
        last_date = datetime.strptime(dates[-1], "%Y-%m-%d")
        pred_dates = []
        d = last_date
        for _ in range(horizon):
            d += timedelta(days=1)
            while d.weekday() >= 5:  # 跳過週末
                d += timedelta(days=1)
            pred_dates.append(d.strftime("%Y-%m-%d"))

        # 可靠度提示
        mape = metrics.get("mape", 100)
        if mape < 3:
            reliability = "高（MAPE < 3%）"
        elif mape < 8:
            reliability = "中（MAPE < 8%）"
        else:
            reliability = "低（MAPE ≥ 8%）"

        result = {
            "symbol": symbol,
            "model": model,
            "model_name": self.MODELS.get(model, model),
            "horizon": horizon,
            "confidence": confidence,
            "forecast_dates": pred_dates,
            "forecast_values": [round(v, 2) for v in forecast["values"]],
            "upper_band": [round(v, 2) for v in upper_band],
            "lower_band": [round(v, 2) for v in lower_band],
            "metrics": metrics,
            "reliability": reliability,
            "disclaimer": self.DISCLAIMER,
            "training_period": f"{dates[0]} ~ {dates[-1]}",
            "data_source": forecast.get("source", "FinMind/TWSE/TPEX"),
            "updated_at": datetime.now().isoformat(),
        }

        # 寫入快取
        _prediction_cache[ck] = result
        if len(_prediction_cache) > _CACHE_MAX:
            _prediction_cache.popitem(last=False)

        return result

    # ===== 模型實作 =====

    def _naive_predict(self, prices: List[float], horizon: int) -> Dict:
        """Naive 預測：最後一個值 + 漂移"""
        n = len(prices)
        last_price = prices[-1]
        # 計算漂移 (drift)
        drift = (prices[-1] - prices[0]) / (n - 1) if n > 1 else 0

        values = []
        for h in range(1, horizon + 1):
            values.append(last_price + drift * h)

        return {"values": values, "source": "Naive (Drift)"}

    def _arima_predict(self, prices: List[float], horizon: int) -> Dict:
        """ARIMA(p,d,q) 預測 - 簡化 AR(1) 實作"""
        # 差分 (d=1)
        diff = [prices[i] - prices[i - 1] for i in range(1, len(prices))]

        if not diff:
            return self._naive_predict(prices, horizon)

        # AR(1) 係數估計
        n = len(diff)
        mean_diff = sum(diff) / n

        # 自相關
        numerator = sum(
            (diff[i] - mean_diff) * (diff[i - 1] - mean_diff) for i in range(1, n)
        )
        denominator = sum((d - mean_diff) ** 2 for d in diff)
        phi = numerator / denominator if denominator != 0 else 0
        phi = max(-0.99, min(0.99, phi))  # 穩定性限制

        # 常數項
        c = mean_diff * (1 - phi)

        # 預測
        last_diff = diff[-1]
        last_price = prices[-1]
        values = []
        current_diff = last_diff

        for _ in range(horizon):
            current_diff = c + phi * current_diff
            last_price = last_price + current_diff
            values.append(last_price)

        return {"values": values, "source": "ARIMA(1,1,0)"}

    def _prophet_predict(
        self, prices: List[float], dates: List[str], horizon: int
    ) -> Dict:
        """Prophet 風格預測 - 趨勢 + 季節性分解"""
        n = len(prices)

        # 趨勢: 線性回歸
        x_mean = (n - 1) / 2
        y_mean = sum(prices) / n
        numerator = sum((i - x_mean) * (prices[i] - y_mean) for i in range(n))
        denominator = sum((i - x_mean) ** 2 for i in range(n))
        slope = numerator / denominator if denominator != 0 else 0
        intercept = y_mean - slope * x_mean

        # 季節性: 週期 5 (交易日/週)
        period = 5
        residuals = [prices[i] - (intercept + slope * i) for i in range(n)]
        seasonal = [0.0] * period
        counts = [0] * period
        for i, r in enumerate(residuals):
            idx = i % period
            seasonal[idx] += r
            counts[idx] += 1
        seasonal = [s / c if c > 0 else 0 for s, c in zip(seasonal, counts)]

        # 預測
        values = []
        for h in range(1, horizon + 1):
            trend_val = intercept + slope * (n - 1 + h)
            season_val = seasonal[(n - 1 + h) % period]
            pred = trend_val + season_val
            values.append(max(0, pred))

        return {"values": values, "source": "Prophet-like (Trend+Seasonal)"}

    # ===== Walk-Forward 驗證 =====

    def _walk_forward_validate(
        self, prices: List[float], model: str, horizon: int
    ) -> Dict[str, float]:
        """Walk-forward 滾動驗證"""
        n = len(prices)
        min_train = max(60, n // 2)
        test_size = min(horizon, n - min_train)

        if test_size <= 0:
            return {"mae": 0, "rmse": 0, "mape": 0}

        errors = []
        abs_errors = []
        pct_errors = []

        steps = min(5, test_size)  # 最多 5 步驗證
        step_size = max(1, test_size // steps)

        for step in range(steps):
            split = min_train + step * step_size
            if split >= n:
                break

            train = prices[:split]
            actual_end = min(split + horizon, n)
            actuals = prices[split:actual_end]

            if not actuals:
                break

            # 預測
            if model == "naive":
                pred_result = self._naive_predict(train, len(actuals))
            elif model == "arima":
                pred_result = self._arima_predict(train, len(actuals))
            else:
                dates_stub = [f"2020-01-{i+1:02d}" for i in range(len(train))]
                pred_result = self._prophet_predict(train, dates_stub, len(actuals))

            preds = pred_result["values"]

            for actual, pred in zip(actuals, preds):
                err = pred - actual
                errors.append(err ** 2)
                abs_errors.append(abs(err))
                if actual != 0:
                    pct_errors.append(abs(err) / abs(actual) * 100)

        if not errors:
            return {"mae": 0, "rmse": 0, "mape": 0}

        mae = sum(abs_errors) / len(abs_errors)
        rmse = math.sqrt(sum(errors) / len(errors))
        mape = sum(pct_errors) / len(pct_errors) if pct_errors else 0

        return {
            "mae": round(mae, 4),
            "rmse": round(rmse, 4),
            "mape": round(mape, 2),
        }


# 單例
prediction_service = PredictionService()
