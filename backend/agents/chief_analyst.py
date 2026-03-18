"""
backend/agents/chief_analyst.py
首席分析師 Agent（Opus 撰寫）

職責：
1. 接收仲裁結果 + 六部門輸出 + 股票基本資訊
2. 透過 Gemini 3 Flash Preview 生成完整繁中投行研報（11 章固定順序）
3. 從報告中提取結構化資料（評級 / 目標價 / SL-TP / 情境概率）
4. 將預測資料寫入 Supabase predictions 表

設計原則：
- 所有 Gemini 呼叫經 BaseAgent.run() → backend.gemini.client
- 部門輸出可能處於任意狀態（成功 / 解析失敗 / 限流 / 錯誤），全部防呆
- 結構化資料提取使用多策略 regex + 啟發式，寧可不提取也不誤提取
- 預測寫入失敗不阻斷報告回傳
"""
import json
import logging
import re
import time
import uuid
from datetime import date, timedelta
from typing import Optional

from backend.agents.base_agent import BaseAgent
from backend.core.audit_log import log_agent_action
from backend.data.storage.supabase_client import insert_row

logger = logging.getLogger(__name__)

# ═════════════════════════════════════════════════════════
# 常量定義
# ═════════════════════════════════════════════════════════

# 評級標準化對照表（長詞優先匹配）
RATING_MAP: dict[str, str] = {
    # 繁體中文
    "強力買入": "strong_buy",
    "強烈買入": "strong_buy",
    "買入":     "buy",
    "買進":     "buy",
    "中性":     "neutral",
    "持有":     "neutral",
    "觀望":     "neutral",
    "賣出":     "sell",
    "強力賣出": "strong_sell",
    "強烈賣出": "strong_sell",
    # 英文（小寫存放，查詢時先 .lower()）
    "strong buy":  "strong_buy",
    "buy":         "buy",
    "hold":        "neutral",
    "neutral":     "neutral",
    "sell":        "sell",
    "strong sell": "strong_sell",
}

# 供 regex 使用的評級關鍵字（長的排前面）
_RATING_KEYWORDS: list[str] = [
    "強力買入", "強烈買入", "強力賣出", "強烈賣出",
    "買入", "買進", "中性", "持有", "觀望", "賣出",
    "Strong Buy", "Strong Sell",
    "Buy", "Sell", "Hold", "Neutral",
]

# 仲裁立場 → 預測方向
_STANCE_TO_DIRECTION: dict[str, str] = {
    "bullish":          "bullish",
    "cautious_bullish": "bullish",
    "neutral":          "neutral",
    "cautious_bearish": "bearish",
    "bearish":          "bearish",
}

# 三個預測時間維度
_TIMEFRAME_SPECS: list[dict] = [
    {"key": "short",  "trading_days": 5,   "label": "短期"},
    {"key": "medium", "trading_days": 30,  "label": "中期"},
    {"key": "long",   "trading_days": 90,  "label": "長期"},
]

# 部門 key → 中文顯示名稱
_DEPT_DISPLAY_NAMES: dict[str, str] = {
    "technical":   "技術分析",
    "fundamental": "基本面研究",
    "chips":       "籌碼分析",
    "event":       "事件驅動",
    "macro":       "宏觀策略",
    "sentiment":   "情緒雷達",
}


class ChiefAnalystAgent(BaseAgent):
    """
    首席分析師 — 整合所有部門輸出與仲裁結果，
    生成完整投行研報並建立可追蹤的預測記錄。
    """

    @property
    def agent_name(self) -> str:
        return "chief_analyst"

    @property
    def use_grounding(self) -> bool:
        return False  # 所有資料由部門提供，不需 Google Search

    # ═════════════════════════════════════════════════════
    # 公開介面
    # ═════════════════════════════════════════════════════

    def generate_report(
        self,
        symbol: str,
        market: str,
        company_name: str,
        industry: str,
        current_price: float,
        technical: dict,
        fundamental: dict,
        chips: dict,
        event: dict,
        macro: dict,
        sentiment: dict,
        arbitration: dict,
        report_id: str = None,
    ) -> dict:
        """
        生成完整投資研究報告。

        流程：
        1. 提取各部門摘要（處理缺失 / 限流 / 解析失敗）
        2. 安全解析仲裁結果
        3. 透過 BaseAgent.run() 呼叫 Gemini 生成 Markdown 報告
        4. 從報告中提取結構化資料（評級 / 目標價 / 進出場 / 情境）
        5. 為三個時間維度建立預測記錄寫入 Supabase
        6. 回傳完整結果

        Returns:
            {
                "status":              "success" | "failed" | "rate_limited",
                "report_id":           str,
                "final_report":        str | None,
                "rating":              str | None,
                "target_price_low":    float | None,
                "target_price_high":   float | None,
                "confidence_score":    float,
                "prediction_ids":      list[str],
                "model_used":          str,
                "duration_ms":         int,
                "total_gemini_calls":  int,
                "error":               str,          # 僅失敗時
            }
        """
        start_time = time.time()
        report_id = report_id or str(uuid.uuid4())

        # ── 1. 提取各部門摘要 ─────────────────────────────
        summaries = {}
        for dept_key, dept_output in [
            ("technical",   technical),
            ("fundamental", fundamental),
            ("chips",       chips),
            ("event",       event),
            ("macro",       macro),
            ("sentiment",   sentiment),
        ]:
            display_name = _DEPT_DISPLAY_NAMES.get(dept_key, dept_key)
            summaries[dept_key] = self._extract_summary(dept_output, display_name)

        # ── 2. 安全解析仲裁結果 ──────────────────────────
        arb = self._safe_parse_arbitration(arbitration)

        # ── 3. 呼叫 Gemini 生成報告 ─────────────────────
        #    使用 BaseAgent.run()，自動處理 prompt 填入 + audit log
        gemini_result = self.run(
            report_id=report_id,
            symbol=symbol,
            market=market,
            company_name=company_name,
            industry=industry,
            current_price=str(current_price),
            report_date=date.today().isoformat(),
            technical_summary=summaries["technical"],
            fundamental_summary=summaries["fundamental"],
            chips_summary=summaries["chips"],
            event_summary=summaries["event"],
            macro_summary=summaries["macro"],
            sentiment_summary=summaries["sentiment"],
            final_stance=arb["final_stance"],
            stance_confidence=str(arb["stance_confidence"]),
            arbitration_summary=arb["arbitration_summary"],
            key_risks=arb["key_risks"],
            key_catalysts=arb["key_catalysts"],
        )

        total_duration = int((time.time() - start_time) * 1000)

        # ── 4. 處理 Gemini 失敗 ──────────────────────────
        if gemini_result["status"] != "success":
            log_agent_action(
                self.agent_name, report_id, gemini_result["status"],
                action="generate_report",
                duration_ms=total_duration,
                error=gemini_result.get("error"),
            )
            return self._build_output(
                status=gemini_result["status"],
                report_id=report_id,
                confidence_score=arb["stance_confidence"],
                model_used=gemini_result.get("model_used", "unknown"),
                duration_ms=total_duration,
                total_gemini_calls=1,
                error=gemini_result.get("error"),
            )

        final_report = gemini_result["output"]

        # ── 5. 提取結構化資料 ────────────────────────────
        structured = self._extract_structured_data(final_report, current_price)

        # ── 6. 寫入預測記錄 ──────────────────────────────
        prediction_ids = self._save_predictions(
            report_id=report_id,
            symbol=symbol,
            market=market,
            structured_data=structured,
            arbitration=arb,
        )

        # ── 7. 記錄成功 & 回傳 ──────────────────────────
        log_agent_action(
            self.agent_name, report_id, "success",
            action="generate_report",
            duration_ms=total_duration,
            metadata={
                "rating": structured["rating"],
                "target_low": structured["target_price_low"],
                "target_high": structured["target_price_high"],
                "prediction_count": len(prediction_ids),
                "model_used": gemini_result.get("model_used"),
            },
        )

        return self._build_output(
            status="success",
            report_id=report_id,
            final_report=final_report,
            rating=structured["rating"],
            target_price_low=structured["target_price_low"],
            target_price_high=structured["target_price_high"],
            confidence_score=arb["stance_confidence"],
            prediction_ids=prediction_ids,
            model_used=gemini_result.get("model_used", "unknown"),
            duration_ms=total_duration,
            total_gemini_calls=1,
        )

    # ═════════════════════════════════════════════════════
    # 部門摘要提取
    # ═════════════════════════════════════════════════════

    @staticmethod
    def _extract_summary(dept_output: dict, dept_name: str) -> str:
        """
        從部門輸出中提取摘要文字，供 Prompt 使用。

        處理四種情況：
        1. None / 空值       → 回傳「不可用」
        2. rate_limited / failed → 回傳「暫時不可用」
        3. 有 summary 欄位   → 直接取用
        4. parse_failed + raw → 截取前 300 字
        5. 完整 dict          → JSON 序列化（截取 600 字）
        """
        if not dept_output or not isinstance(dept_output, dict):
            return f"（{dept_name}部門資料不可用）"

        status = dept_output.get("status")
        has_summary = bool(dept_output.get("summary"))

        # 失敗 / 限流且無 summary
        if status in ("rate_limited", "failed") and not has_summary:
            error_hint = dept_output.get("error", "")
            suffix = f"：{error_hint[:80]}" if error_hint else ""
            return f"（{dept_name}部門暫時不可用{suffix}）"

        # 優先取 summary 欄位
        if has_summary:
            return str(dept_output["summary"])

        # parse_failed 情況
        if dept_output.get("parse_failed") and dept_output.get("raw"):
            raw = str(dept_output["raw"])
            return raw[:300] + ("..." if len(raw) > 300 else "")

        # 完整 dict — 移除內部 meta 欄位後序列化
        try:
            cleaned = {
                k: v for k, v in dept_output.items()
                if not k.startswith("_")
                and k not in ("parse_failed", "status", "error")
            }
            serialized = json.dumps(cleaned, ensure_ascii=False, indent=1)
            if len(serialized) > 600:
                return serialized[:600] + "\n... (已截取)"
            return serialized
        except (TypeError, ValueError):
            return f"（{dept_name}部門資料解析失敗）"

    # ═════════════════════════════════════════════════════
    # 仲裁結果安全解析
    # ═════════════════════════════════════════════════════

    @staticmethod
    def _safe_parse_arbitration(arbitration: dict) -> dict:
        """
        安全解析仲裁輸出。

        無論仲裁輸出是已解析的 dict、含 parse_failed 的 raw 文字、
        或者直接是 failed 狀態，都回傳統一結構。
        """
        defaults = {
            "final_stance":        "neutral",
            "stance_confidence":   0.5,
            "arbitration_summary": "仲裁結果暫時不可用",
            "key_risks":           "未知",
            "key_catalysts":       "未知",
            "conflicts_detected":  [],
        }

        if not arbitration or not isinstance(arbitration, dict):
            return defaults

        # 失敗狀態
        if arbitration.get("status") in ("rate_limited", "failed", "insufficient_data"):
            return defaults

        # parse_failed 情況 — 嘗試從 raw 中提取 JSON
        if arbitration.get("parse_failed") and "raw" in arbitration:
            parsed = _try_extract_json_from_text(str(arbitration["raw"]))
            if parsed and isinstance(parsed, dict):
                arbitration = parsed

        # 提取 final_stance（驗證合法性）
        final_stance = arbitration.get("final_stance", "neutral")
        if final_stance not in _STANCE_TO_DIRECTION:
            final_stance = "neutral"

        # 提取並夾緊 confidence
        try:
            stance_confidence = float(arbitration.get("stance_confidence", 0.5))
            stance_confidence = max(0.0, min(1.0, stance_confidence))
        except (TypeError, ValueError):
            stance_confidence = 0.5

        # key_risks / key_catalysts：list → 分號串聯字串
        key_risks = arbitration.get("key_risks", defaults["key_risks"])
        if isinstance(key_risks, list):
            key_risks = "；".join(str(r) for r in key_risks if r)

        key_catalysts = arbitration.get("key_catalysts", defaults["key_catalysts"])
        if isinstance(key_catalysts, list):
            key_catalysts = "；".join(str(c) for c in key_catalysts if c)

        return {
            "final_stance":        final_stance,
            "stance_confidence":   stance_confidence,
            "arbitration_summary": str(
                arbitration.get("arbitration_summary", defaults["arbitration_summary"])
            ),
            "key_risks":           key_risks,
            "key_catalysts":       key_catalysts,
            "conflicts_detected":  arbitration.get("conflicts_detected", []),
        }

    # ═════════════════════════════════════════════════════
    # 結構化資料提取（從 Markdown 報告）
    # ═════════════════════════════════════════════════════

    def _extract_structured_data(
        self, report_text: str, current_price: float
    ) -> dict:
        """
        從生成的 Markdown 報告中提取結構化資訊。

        多策略 regex + 啟發式解析：
        - 第一章（市場快報） → 評級、目標價
        - 第七章（進出場計畫）→ 各時間維度的 SL/TP/R:R
        - 第九章（結論）      → 備用評級
        - 第十章（情境地圖）  → Bull/Base/Bear 概率 & 目標

        Returns:
            {
                "rating":            str | None,
                "target_price_low":  float | None,
                "target_price_high": float | None,
                "entry_plans":       dict,
                "scenarios":         dict,
            }
        """
        result = {
            "rating":            None,
            "target_price_low":  None,
            "target_price_high": None,
            "entry_plans":       {},
            "scenarios":         {},
        }

        if not report_text:
            return result

        result["rating"] = self._extract_rating(report_text)
        low, high = self._extract_target_prices(report_text, current_price)
        result["target_price_low"] = low
        result["target_price_high"] = high
        result["entry_plans"] = self._extract_entry_plans(report_text)
        result["scenarios"] = self._extract_scenarios(report_text)

        return result

    # ── 評級提取 ─────────────────────────────────────────

    @staticmethod
    def _extract_rating(report_text: str) -> Optional[str]:
        """
        從報告中提取評級並標準化。

        搜尋策略（按優先順序）：
        1. 「評級」關鍵字後緊跟的評級詞
        2. 第一章（市場快報）內出現的評級詞
        3. 第九章（結論）內出現的評級詞
        """
        # 策略 1：找「評級」後面的詞（最可靠）
        for kw in _RATING_KEYWORDS:
            # 支援：評級：買入 / 評級: 買入 / 評級 「買入」 / 投資評級：買入
            pattern = rf"(?:投資)?評級[：:\s]*[「「]?({re.escape(kw)})[」」]?"
            match = re.search(pattern, report_text, re.IGNORECASE)
            if match:
                found = match.group(1).strip()
                return RATING_MAP.get(found, RATING_MAP.get(found.lower()))

        # 策略 2：在第一章範圍內找
        ch1_match = re.search(
            r"(?:第一章|##\s*.*?市場快報)(.*?)(?=##\s|\Z)",
            report_text, re.DOTALL
        )
        if ch1_match:
            ch1_text = ch1_match.group(1)
            for kw in _RATING_KEYWORDS:
                if kw in ch1_text:
                    return RATING_MAP.get(kw, RATING_MAP.get(kw.lower()))
                if kw.lower() in ch1_text.lower():
                    return RATING_MAP.get(kw.lower())

        # 策略 3：在結論章節找
        conclusion_match = re.search(
            r"(?:第九章|##\s*.*?結論)(.*?)(?=##\s|\Z)",
            report_text, re.DOTALL
        )
        if conclusion_match:
            conc_text = conclusion_match.group(1)
            for kw in _RATING_KEYWORDS:
                if kw in conc_text:
                    return RATING_MAP.get(kw, RATING_MAP.get(kw.lower()))
                if kw.lower() in conc_text.lower():
                    return RATING_MAP.get(kw.lower())

        return None

    # ── 目標價提取 ───────────────────────────────────────

    @staticmethod
    def _extract_target_prices(
        report_text: str, current_price: float
    ) -> tuple[Optional[float], Optional[float]]:
        """
        從報告中提取目標價低點和高點。

        多策略匹配（按優先順序）：
        1. 目標價 X ~ Y（區間格式）
        2. 情境地圖 Base/Bull/Bear 目標
        3. 單獨出現的「目標價 X」

        防呆：提取的價格必須在 current_price 的 0.3x ~ 3.0x 內。
        """
        candidates: list[tuple[float, float]] = []

        # ── 模式 1：目標價區間（X ~ Y / X-Y / X 至 Y）───
        range_patterns = [
            r"目標價[區間範圍：:\s]*(?:約?\s*)?(?:NT?\$?\s*)?(\d[\d,.]*)\s*[~～\-–—至到]\s*(?:NT?\$?\s*)?(\d[\d,.]*)",
            r"目標[價][：:\s]*(?:約?\s*)?(?:NT?\$?\s*)?(\d[\d,.]*)\s*[~～\-–—至到]\s*(?:NT?\$?\s*)?(\d[\d,.]*)",
        ]
        for pat in range_patterns:
            for m in re.finditer(pat, report_text):
                low = _parse_number(m.group(1))
                high = _parse_number(m.group(2))
                if low is not None and high is not None:
                    if low > high:
                        low, high = high, low
                    candidates.append((low, high))

        # ── 模式 2：情境地圖目標 ─────────────────────────
        ch10_match = re.search(
            r"(?:第十章|##\s*.*?情境地圖)(.*?)(?=##\s*(?:第十一|.*?可解釋)|\Z)",
            report_text, re.DOTALL
        )
        if ch10_match:
            ch10_text = ch10_match.group(1)
            bull_target = _find_scenario_target(ch10_text, [r"偏多情境", r"Bull Case"])
            base_target = _find_scenario_target(ch10_text, [r"基本情境", r"Base Case"])
            bear_target = _find_scenario_target(ch10_text, [r"偏空情境", r"Bear Case"])

            if bear_target and bull_target:
                candidates.append((min(bear_target, bull_target),
                                   max(bear_target, bull_target)))
            elif base_target and bull_target:
                candidates.append((min(base_target, bull_target),
                                   max(base_target, bull_target)))
            elif base_target:
                candidates.append((base_target * 0.95, base_target * 1.05))

        # ── 模式 3：單一目標價 ───────────────────────────
        single_pattern = r"目標價[：:\s]*(?:約?\s*)?(?:NT?\$?\s*)?(\d[\d,.]*)\s*(?:元|點)?"
        single_all = re.findall(single_pattern, report_text)
        parsed_singles = [_parse_number(s) for s in single_all]
        parsed_singles = [v for v in parsed_singles if v is not None and v > 0]
        if len(parsed_singles) >= 2:
            candidates.append((min(parsed_singles), max(parsed_singles)))
        elif len(parsed_singles) == 1:
            val = parsed_singles[0]
            candidates.append((val * 0.95, val * 1.05))

        # ── 從候選中選出最合理的 ─────────────────────────
        if not candidates:
            return None, None

        # 合理性過濾
        valid: list[tuple[float, float]] = []
        for low, high in candidates:
            if current_price > 0:
                ratio_low = low / current_price
                ratio_high = high / current_price
                if 0.3 <= ratio_low <= 3.0 and 0.3 <= ratio_high <= 3.0:
                    valid.append((low, high))
            else:
                valid.append((low, high))

        if valid:
            return valid[0]  # 第一組（來自最高優先模式）

        # 所有候選都不合理：回傳第一組（有勝於無）
        return candidates[0]

    # ── 進出場計畫提取 ───────────────────────────────────

    @staticmethod
    def _extract_entry_plans(report_text: str) -> dict:
        """
        從第七章（進出場計畫）提取各時間維度的 SL / TP / R:R。

        Returns:
            {
                "short":  {"sl": float|None, "tp": float|None, "rr": str|None},
                "medium": {"sl": float|None, "tp": float|None, "rr": str|None},
                "long":   {"sl": float|None, "tp": float|None, "rr": str|None},
            }
        """
        empty_plan = {"sl": None, "tp": None, "rr": None}
        plans = {
            "short":  dict(empty_plan),
            "medium": dict(empty_plan),
            "long":   dict(empty_plan),
        }

        # 定位第七章
        ch7_match = re.search(
            r"(?:第七章|##\s*.*?進出場計畫)(.*?)(?=##\s*(?:第八|.*?風險提示)|\Z)",
            report_text, re.DOTALL
        )
        if not ch7_match:
            return plans

        ch7_text = ch7_match.group(1)

        # 分割成短 / 中 / 長期區段
        section_defs = {
            "short": {
                "start": [r"短期", r"1[\-\~]5\s*(?:個)?交易日", r"Short[\s\-]*[Tt]erm"],
                "end":   [r"中期", r"2[\-\~]6\s*週", r"Medium[\s\-]*[Tt]erm"],
            },
            "medium": {
                "start": [r"中期", r"2[\-\~]6\s*週", r"Medium[\s\-]*[Tt]erm"],
                "end":   [r"長期", r"2[\-\~]4\s*季", r"Long[\s\-]*[Tt]erm"],
            },
            "long": {
                "start": [r"長期", r"2[\-\~]4\s*季", r"Long[\s\-]*[Tt]erm"],
                "end":   [],
            },
        }

        for tf_key, defs in section_defs.items():
            section_text = _extract_between(
                ch7_text, defs["start"], defs["end"]
            )
            if not section_text:
                continue
            plans[tf_key] = {
                "sl": _extract_price_near_keyword(
                    section_text, [r"止損", r"停損", r"SL", r"Stop\s*Loss"]
                ),
                "tp": _extract_price_near_keyword(
                    section_text, [r"止盈", r"停利", r"TP", r"Take\s*Profit", r"目標"]
                ),
                "rr": _extract_risk_reward(section_text),
            }

        return plans

    # ── 情境地圖提取 ─────────────────────────────────────

    @staticmethod
    def _extract_scenarios(report_text: str) -> dict:
        """
        從第十章（情境地圖）提取 Bull / Base / Bear 概率和目標價。

        Returns:
            {
                "bull": {"probability": float|None, "target": float|None},
                "base": {"probability": float|None, "target": float|None},
                "bear": {"probability": float|None, "target": float|None},
            }
        """
        scenarios = {
            "bull": {"probability": None, "target": None},
            "base": {"probability": None, "target": None},
            "bear": {"probability": None, "target": None},
        }

        ch10_match = re.search(
            r"(?:第十章|##\s*.*?情境地圖)(.*?)(?=##\s*(?:第十一|.*?可解釋)|\Z)",
            report_text, re.DOTALL
        )
        if not ch10_match:
            return scenarios

        ch10_text = ch10_match.group(1)

        scenario_keywords = {
            "bull": [r"偏多情境", r"Bull\s*Case"],
            "base": [r"基本情境", r"Base\s*Case"],
            "bear": [r"偏空情境", r"Bear\s*Case"],
        }

        for sc_key, keywords in scenario_keywords.items():
            for kw in keywords:
                # 提取概率：找 kw 所在行或附近的 XX%
                prob_pattern = rf"{kw}[^%\n]*?(\d{{1,3}})\s*%"
                prob_match = re.search(prob_pattern, ch10_text, re.IGNORECASE)
                if prob_match:
                    prob = float(prob_match.group(1))
                    if 0 < prob <= 100:
                        scenarios[sc_key]["probability"] = prob
                    break

            # 提取目標價
            target = _find_scenario_target(ch10_text, keywords)
            if target:
                scenarios[sc_key]["target"] = target

        return scenarios

    # ═════════════════════════════════════════════════════
    # 預測記錄寫入
    # ═════════════════════════════════════════════════════

    def _save_predictions(
        self,
        report_id: str,
        symbol: str,
        market: str,
        structured_data: dict,
        arbitration: dict,
    ) -> list[str]:
        """
        根據報告的結構化資料，建立三個時間維度的預測記錄。

        預測方向由仲裁的 final_stance 決定。
        目標價優先使用各時間維度的進出場計畫 TP/SL，
        降級為報告整體目標價。

        Returns:
            成功寫入的 prediction UUID 列表
        """
        prediction_ids: list[str] = []
        today = date.today()

        # 預測方向
        stance = arbitration.get("final_stance", "neutral")
        predicted_direction = _STANCE_TO_DIRECTION.get(stance, "neutral")

        for spec in _TIMEFRAME_SPECS:
            tf_key = spec["key"]
            trading_days = spec["trading_days"]
            verify_date = self._add_trading_days(today, trading_days)

            # 決定該時間維度的目標價
            target_low, target_high = self._resolve_timeframe_targets(
                tf_key, structured_data
            )

            prediction_data = {
                "report_id":           report_id,
                "symbol":              symbol,
                "market":              market,
                "predicted_direction":  predicted_direction,
                "predicted_target_low": target_low,
                "predicted_target_high": target_high,
                "timeframe":           tf_key,
                "prediction_date":     today.isoformat(),
                "verify_date":         verify_date.isoformat(),
                "is_verified":         False,
            }

            row = insert_row("predictions", prediction_data)
            if row and row.get("id"):
                prediction_ids.append(row["id"])
                logger.info(
                    f"[ChiefAnalyst] 建立預測 {tf_key}: "
                    f"{symbol} {predicted_direction} "
                    f"({target_low} ~ {target_high}), "
                    f"verify={verify_date}"
                )
            else:
                logger.warning(
                    f"[ChiefAnalyst] 預測寫入失敗 ({tf_key}): "
                    f"Supabase 可能不可用"
                )

        if prediction_ids:
            logger.info(
                f"[ChiefAnalyst] 共寫入 {len(prediction_ids)} 筆預測 "
                f"for {symbol}"
            )

        return prediction_ids

    @staticmethod
    def _resolve_timeframe_targets(
        timeframe_key: str, structured_data: dict
    ) -> tuple[Optional[float], Optional[float]]:
        """
        依據時間維度決定預測目標價。

        優先級：
        1. 進出場計畫的 SL（低）+ TP（高）
        2. 情境地圖的 Bear target（低）+ Bull target（高）
        3. 報告整體目標價
        """
        entry_plans = structured_data.get("entry_plans", {})
        plan = entry_plans.get(timeframe_key, {})

        tp = plan.get("tp")
        sl = plan.get("sl")

        # 優先使用進出場計畫
        if sl is not None and tp is not None:
            return (min(sl, tp), max(sl, tp))
        if tp is not None:
            overall_low = structured_data.get("target_price_low")
            if overall_low is not None:
                return (min(overall_low, tp), max(overall_low, tp))
            return (tp * 0.95, tp * 1.05)

        # 嘗試情境地圖
        scenarios = structured_data.get("scenarios", {})
        bear_target = (scenarios.get("bear") or {}).get("target")
        bull_target = (scenarios.get("bull") or {}).get("target")
        if bear_target and bull_target:
            return (min(bear_target, bull_target), max(bear_target, bull_target))

        # 降級為整體目標價
        overall_low = structured_data.get("target_price_low")
        overall_high = structured_data.get("target_price_high")
        if overall_low is not None and overall_high is not None:
            return (overall_low, overall_high)

        return (None, None)

    # ═════════════════════════════════════════════════════
    # 交易日計算
    # ═════════════════════════════════════════════════════

    @staticmethod
    def _add_trading_days(from_date: date, trading_days: int) -> date:
        """
        從指定日期加上 N 個交易日（跳過週末）。

        簡化版本，不考慮各國交易所假日。
        後續版本可整合假日日曆以提升精確度。
        """
        if trading_days <= 0:
            return from_date

        current = from_date
        added = 0
        while added < trading_days:
            current += timedelta(days=1)
            if current.weekday() < 5:  # 0=Mon ... 4=Fri
                added += 1

        return current

    # ═════════════════════════════════════════════════════
    # 標準化輸出組裝
    # ═════════════════════════════════════════════════════

    @staticmethod
    def _build_output(
        status: str,
        report_id: str = "",
        final_report: Optional[str] = None,
        rating: Optional[str] = None,
        target_price_low: Optional[float] = None,
        target_price_high: Optional[float] = None,
        confidence_score: float = 0.5,
        prediction_ids: Optional[list] = None,
        model_used: str = "",
        duration_ms: int = 0,
        total_gemini_calls: int = 0,
        error: Optional[str] = None,
    ) -> dict:
        """組裝標準化輸出 dict。"""
        output = {
            "status":              status,
            "report_id":           report_id,
            "final_report":        final_report,
            "rating":              rating,
            "target_price_low":    target_price_low,
            "target_price_high":   target_price_high,
            "confidence_score":    confidence_score,
            "prediction_ids":      prediction_ids or [],
            "model_used":          model_used,
            "duration_ms":         duration_ms,
            "total_gemini_calls":  total_gemini_calls,
        }
        if error:
            output["error"] = error
        return output


# ═════════════════════════════════════════════════════════
# 模組級私有輔助函式
# ═════════════════════════════════════════════════════════

def _parse_number(text: str) -> Optional[float]:
    """安全解析數字字串，處理逗號分隔（如 1,234.56）。"""
    if not text:
        return None
    try:
        cleaned = text.replace(",", "").replace("，", "").strip()
        return float(cleaned)
    except (ValueError, TypeError):
        return None


def _try_extract_json_from_text(text: str) -> Optional[dict]:
    """
    嘗試從混合文字中提取 JSON 物件。
    先找 ```json``` 區塊，再找 { } 配對。
    """
    # 嘗試 markdown code block
    code_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
    if code_match:
        try:
            return json.loads(code_match.group(1))
        except json.JSONDecodeError:
            pass

    # 嘗試直接找 JSON 物件（追蹤大括號深度）
    brace_start = text.find("{")
    if brace_start == -1:
        return None

    depth = 0
    for i in range(brace_start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[brace_start:i + 1])
                except json.JSONDecodeError:
                    return None

    return None


def _extract_between(
    text: str,
    start_keywords: list[str],
    end_keywords: list[str],
) -> Optional[str]:
    """
    從 text 中提取 start_keywords 與 end_keywords 之間的文字。
    keywords 為 OR 關係，取第一個匹配的。
    """
    # 找 start
    start_pos = None
    for kw in start_keywords:
        m = re.search(kw, text, re.IGNORECASE)
        if m:
            start_pos = m.start()
            break

    if start_pos is None:
        return None

    # 找 end（在 start 之後）
    if not end_keywords:
        return text[start_pos:]

    end_pos = len(text)
    for kw in end_keywords:
        m = re.search(kw, text[start_pos + 1:], re.IGNORECASE)
        if m:
            candidate = start_pos + 1 + m.start()
            end_pos = min(end_pos, candidate)

    return text[start_pos:end_pos]


def _extract_price_near_keyword(
    text: str, keywords: list[str]
) -> Optional[float]:
    """
    在 text 中找到 keyword 附近的第一個數字（價格）。
    搜尋 keyword 後方最近的數字。
    """
    for kw in keywords:
        pattern = rf"{kw}[（(：:\s]*(?:約?\s*)?(?:NT?\$?\s*)?(\d[\d,.]*)"
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            val = _parse_number(match.group(1))
            if val is not None and val > 0:
                return val

    return None


def _extract_risk_reward(text: str) -> Optional[str]:
    """提取風報比（R:R），如 "1:2.5"。"""
    patterns = [
        r"(?:風報比|R\s*[：:]\s*R|Risk\s*[：:]\s*Reward)[（(：:\s]*"
        r"(\d+(?:\.\d+)?\s*[：:]\s*\d+(?:\.\d+)?)",
        r"(\d+(?:\.\d+)?\s*[：:]\s*\d+(?:\.\d+)?)\s*(?:風報比|R\s*[：:]\s*R)",
    ]
    for pat in patterns:
        match = re.search(pat, text, re.IGNORECASE)
        if match:
            return match.group(1).replace("：", ":").strip()

    return None


def _find_scenario_target(ch10_text: str, keywords: list[str]) -> Optional[float]:
    """
    在情境地圖文字中找到特定情境的目標價。
    """
    for kw in keywords:
        # 找該情境的區段（到下一個情境或結尾）
        section_pat = rf"({kw}.*?)(?=偏多|偏空|基本|Bull|Base|Bear|##|\Z)"
        section_match = re.search(section_pat, ch10_text, re.DOTALL | re.IGNORECASE)
        if not section_match:
            continue

        section_text = section_match.group(1)

        # 找目標價（多種表述）
        target_patterns = [
            r"目標價[上限下行]*[：:\s]*(?:約?\s*)?(?:NT?\$?\s*)?(\d[\d,.]*)",
            r"目標[：:\s]*(?:約?\s*)?(?:NT?\$?\s*)?(\d[\d,.]*)",
            r"(\d[\d,.]*)\s*(?:元|點)",
        ]
        for tpat in target_patterns:
            tmatch = re.search(tpat, section_text)
            if tmatch:
                val = _parse_number(tmatch.group(1))
                if val is not None and val > 0:
                    return val

    return None
