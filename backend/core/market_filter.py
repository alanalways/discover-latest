"""
backend/core/market_filter.py
本地規則過濾器（兩階段掃描的第一階段）

職責：
  對 ~500 支股票進行零 API 呼叫的本地規則過濾，
  快速從 500 支縮減至 50-150 支候選股。

篩選規則（任一成立即入選）：
  1. RSI(14) < 30（超賣）或 > 70（超買）
  2. 今日成交量 > 20 日均量 × 2（爆量）
  3. 今日漲跌幅絕對值 > 3%（大幅波動）
  4. 收盤價突破 MA20 或 MA60（均線突破）
  5. 外資連續買超或賣超 3 日（法人持續動作）
  6. 融資增減幅 > ±5%（散戶信心變化）

設計原則：
  - 純 Python 計算，0 API 呼叫，毫秒完成
  - 輸入資料已由 FinMind 批次取得
  - 不確定的資料（如缺少歷史）跳過該條件，不直接淘汰
"""
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def compute_rsi(closes: list[float], period: int = 14) -> Optional[float]:
    """
    計算 RSI(14)。

    Args:
        closes: 收盤價列表（由舊到新）
        period: RSI 週期（預設 14）

    Returns:
        RSI 值（0-100），資料不足時回傳 None。
    """
    if len(closes) < period + 1:
        return None

    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains = [d if d > 0 else 0 for d in deltas]
    losses = [-d if d < 0 else 0 for d in deltas]

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    for i in range(period, len(deltas)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

    if avg_loss == 0:
        return 100.0

    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 2)


def compute_ma(closes: list[float], period: int) -> Optional[float]:
    """計算移動平均。資料不足回傳 None。"""
    if len(closes) < period:
        return None
    return sum(closes[-period:]) / period


def compute_volume_ratio(volumes: list[int]) -> Optional[float]:
    """
    計算今日成交量 / 20 日均量。

    Args:
        volumes: 成交量列表（由舊到新，最後一個為今日）

    Returns:
        今日量 / 20 日均量，資料不足回傳 None。
    """
    if len(volumes) < 21:
        return None
    avg_20 = sum(volumes[-21:-1]) / 20
    if avg_20 == 0:
        return None
    return volumes[-1] / avg_20


def filter_candidates(
    stocks: list[tuple[str, str]],
    price_map: dict[str, dict],
    chips_map: Optional[dict[str, dict]] = None,
    max_candidates: int = 150,
) -> list[dict]:
    """
    本地規則過濾：從 ~500 支股票篩選出 50-150 支候選股。

    Args:
        stocks:         [(symbol, market), ...] 完整股票清單
        price_map:      {symbol: {closes: [...], volumes: [...], ...}}
                        由 FinMind 批次取得的價格資料
        chips_map:      {symbol: {foreign_net: [...], margin_balance: [...], ...}}
                        台股籌碼資料（可選，有的話效果更好）
        max_candidates: 最多回傳幾支候選（避免 NVIDIA 階段工作量過大）

    Returns:
        [
            {
                "symbol":    str,
                "market":    str,
                "signals":   list[str],  # 觸發的條件說明
                "rsi":       float | None,
                "vol_ratio": float | None,
                "change_pct":float | None,
                "ma_break":  str | None,  # "above_ma20" / "above_ma60" / None
            },
            ...
        ]
    """
    candidates = []

    for symbol, market in stocks:
        price = price_map.get(symbol, {})
        closes  = price.get("closes", [])
        volumes = price.get("volumes", [])

        if not closes or len(closes) < 2:
            continue  # 無資料，跳過

        signals = []

        # ── 條件 1: RSI ────────────────────────────────────
        rsi = compute_rsi(closes)
        if rsi is not None:
            if rsi < 30:
                signals.append(f"RSI超賣({rsi:.1f})")
            elif rsi > 70:
                signals.append(f"RSI超買({rsi:.1f})")

        # ── 條件 2: 成交量爆量 ─────────────────────────────
        vol_ratio = compute_volume_ratio(volumes) if volumes else None
        if vol_ratio is not None and vol_ratio > 2.0:
            signals.append(f"爆量({vol_ratio:.1f}x均量)")

        # ── 條件 3: 今日漲跌幅 > ±3% ─────────────────────
        change_pct = None
        if len(closes) >= 2 and closes[-2] != 0:
            change_pct = (closes[-1] - closes[-2]) / closes[-2] * 100
            if abs(change_pct) > 3.0:
                signals.append(f"大幅波動({change_pct:+.1f}%)")

        # ── 條件 4: 均線突破 ───────────────────────────────
        ma_break = None
        ma20 = compute_ma(closes[:-1], 20)  # 昨日 MA20
        ma60 = compute_ma(closes[:-1], 60)  # 昨日 MA60
        today = closes[-1]
        yesterday = closes[-2] if len(closes) >= 2 else None

        if ma20 and yesterday and today > ma20 and yesterday <= ma20:
            signals.append("突破MA20")
            ma_break = "above_ma20"
        elif ma60 and yesterday and today > ma60 and yesterday <= ma60:
            signals.append("突破MA60")
            ma_break = "above_ma60"

        # ── 條件 5 & 6: 籌碼（台股才有）─────────────────
        if chips_map and market in ("TW", "TWO"):
            chips = chips_map.get(symbol, {})

            foreign_net = chips.get("foreign_net", [])
            if len(foreign_net) >= 3:
                recent = foreign_net[-3:]
                if all(x > 0 for x in recent):
                    signals.append("外資連買3日")
                elif all(x < 0 for x in recent):
                    signals.append("外資連賣3日")

            margin = chips.get("margin_balance", [])
            if len(margin) >= 2 and margin[-2] != 0:
                margin_chg = (margin[-1] - margin[-2]) / abs(margin[-2]) * 100
                if abs(margin_chg) > 5.0:
                    signals.append(f"融資變動({margin_chg:+.1f}%)")

        # ── 入選判斷 ───────────────────────────────────────
        if signals:
            candidates.append({
                "symbol":     symbol,
                "market":     market,
                "signals":    signals,
                "rsi":        rsi,
                "vol_ratio":  vol_ratio,
                "change_pct": change_pct,
                "ma_break":   ma_break,
                "signal_count": len(signals),
            })

    # 依觸發訊號數量排序（訊號越多優先度越高），取前 max_candidates
    candidates.sort(key=lambda x: x["signal_count"], reverse=True)
    result = candidates[:max_candidates]

    logger.info(
        f"[MarketFilter] 過濾完成: {len(stocks)} 支 → {len(result)} 支候選"
        f"（觸發訊號最多 {result[0]['signal_count'] if result else 0} 個）"
    )
    return result


def score_candidates_with_nvidia(
    candidates: list[dict],
    max_top: int = 20,
) -> list[dict]:
    """
    NVIDIA 快速評分（兩階段掃描的第二階段）。

    對 50-150 支候選股，每支用 1 次 NVIDIA 呼叫做快速評分（1-10）。
    取評分最高的 max_top 支，作為完整分析的對象。

    Args:
        candidates: filter_candidates() 的輸出
        max_top:    最多取幾支（預設 20）

    Returns:
        評分結果列表（含 score, signal, reason），已依分數降序排列。
    """
    from backend.nvidia.client import call_nvidia

    scored = []
    for c in candidates:
        symbol    = c["symbol"]
        market    = c["market"]
        signals   = ", ".join(c["signals"])
        rsi_str   = f"RSI={c['rsi']:.1f}" if c["rsi"] else "RSI=N/A"
        vol_str   = f"量比={c['vol_ratio']:.1f}x" if c["vol_ratio"] else "量比=N/A"
        chg_str   = f"漲跌={c['change_pct']:+.1f}%" if c["change_pct"] else "漲跌=N/A"

        prompt = (
            f"股票：{symbol}（{market} 市場）\n"
            f"技術訊號：{signals}\n"
            f"數值：{rsi_str}，{vol_str}，{chg_str}\n\n"
            f"請根據以上技術訊號對這支股票進行快速評估。\n"
            f"只輸出以下 JSON，不要輸出任何其他文字：\n"
            f'{{\"score\": 1-10, \"signal\": \"buy|hold|sell\", \"reason\": \"一句話說明\"}}'
        )

        try:
            result = call_nvidia(
                agent_name="scanner",
                prompt=prompt,
                max_tokens=100,  # 輸出很短
            )
            if result["status"] == "success" and result.get("output"):
                import json
                output = result["output"].strip()
                # 移除可能的 markdown
                if output.startswith("```"):
                    lines = output.split("\n")
                    output = "\n".join(l for l in lines if not l.startswith("```")).strip()
                parsed = json.loads(output)
                scored.append({
                    **c,
                    "score":  parsed.get("score", 5),
                    "signal": parsed.get("signal", "hold"),
                    "reason": parsed.get("reason", ""),
                })
            else:
                # API 失敗，給中性分
                scored.append({**c, "score": 5, "signal": "hold", "reason": "評分失敗"})
        except Exception as e:
            logger.warning(f"[MarketFilter] {symbol} NVIDIA 評分失敗: {e}")
            scored.append({**c, "score": 5, "signal": "hold", "reason": "評分失敗"})

    # 依分數降序排列
    scored.sort(key=lambda x: x.get("score", 0), reverse=True)
    return scored[:max_top]
