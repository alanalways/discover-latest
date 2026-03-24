"""
backend/agents/arbitrator.py
矛盾仲裁官（Opus 撰寫）

職責：
1. 接收六個部門的 JSON 輸出（technical/fundamental/chips/event/macro/sentiment）
2. 執行信號對齊預掃描，計算初步一致性
3. 呼叫 Gemini 3 Flash Preview 執行矛盾識別與仲裁
4. 解析輸出，驗證合法性，補全缺失欄位
5. Gemini 完全失敗時降級為規則引擎做簡易仲裁

設計決策：
- 部門輸出可能是結構化 JSON dict，也可能是 {"status": "failed"} 或含
  "parse_failed" 的原始文字。前處理階段統一處理這些情境。
- 規則引擎仲裁權重反映短中期交易場景：籌碼 > 基本面 > 事件 > 技術 > 宏觀 > 情緒。
- 所有回傳一律包含完整欄位結構，上層不需做 None check。
"""

import json
import logging
import re
import time
from typing import Any, Optional

from backend.agents.base_agent import BaseAgent
from backend.core.audit_log import log_agent_action

logger = logging.getLogger(__name__)

# ─── 常量 ──────────────────────────────────────────────────────

VALID_STANCES = frozenset({
    "bullish", "cautious_bullish", "neutral",
    "cautious_bearish", "bearish",
})

DEPARTMENT_NAMES = (
    "technical", "fundamental", "chips",
    "event", "macro", "sentiment",
)

# 部門 agent_name 對應（prompt 中使用的名稱 <-> arbitrate() 參數名）
_DEPT_AGENT_NAME = {
    "technical":   "technical_agent",
    "fundamental": "fundamental_agent",
    "chips":       "chips_agent",
    "event":       "event_agent",
    "macro":       "macro_agent",
    "sentiment":   "sentiment_agent",
}

# 規則引擎的信號方向 → 數值
_SIGNAL_SCORE = {
    "bullish":          +1.0,
    "cautious_bullish": +0.5,
    "neutral":           0.0,
    "cautious_bearish": -0.5,
    "bearish":          -1.0,
}

# 規則引擎的部門加權
_DEPT_WEIGHT = {
    "technical":   1.0,
    "fundamental": 1.2,
    "chips":       1.3,
    "event":       1.1,
    "macro":       0.9,
    "sentiment":   0.8,
}

# 最低有效部門數門檻
_MIN_VALID_DEPTS = 3

# 傳給 Gemini 的單一部門輸出最大字元數（防 token 爆量）
_MAX_DEPT_CHARS = 3000


# ─── ArbitratorAgent ───────────────────────────────────────────

class ArbitratorAgent(BaseAgent):
    """矛盾仲裁官：整合六部門分析，識別矛盾，輸出最終立場。"""

    @property
    def agent_name(self) -> str:
        return "arbitrator"

    @property
    def use_grounding(self) -> bool:
        return False

    # ── 公開介面 ────────────────────────────────────────────

    def arbitrate(
        self,
        technical: dict,
        fundamental: dict,
        chips: dict,
        event: dict,
        macro: dict,
        sentiment: dict,
        report_id: str = None,
    ) -> dict:
        """
        執行矛盾仲裁。

        Args:
            technical:   技術分析官輸出 dict
            fundamental: 基本面研究官輸出 dict
            chips:       籌碼分析官輸出 dict
            event:       事件驅動官輸出 dict
            macro:       宏觀策略官輸出 dict
            sentiment:   情緒雷達官輸出 dict
            report_id:   關聯報告 UUID

        Returns:
            完整仲裁結果 dict（結構見 _build_output_skeleton）
        """
        start = time.time()

        # 把六個部門打包，方便統一處理
        raw_depts = {
            "technical":   technical,
            "fundamental": fundamental,
            "chips":       chips,
            "event":       event,
            "macro":       macro,
            "sentiment":   sentiment,
        }

        # ── Step 1：前處理，標記有效 / 缺失部門 ──────────
        valid_outputs, missing_depts = self._preprocess_depts(raw_depts)

        valid_count = len(valid_outputs)
        if valid_count < _MIN_VALID_DEPTS:
            duration_ms = int((time.time() - start) * 1000)
            logger.warning(
                f"[Arbitrator] 有效部門僅 {valid_count} 個 "
                f"（缺失: {missing_depts}），資料不足"
            )
            log_agent_action(
                self.agent_name, report_id, "insufficient_data",
                action="arbitrate", duration_ms=duration_ms,
                metadata={"valid": valid_count, "missing": missing_depts},
            )
            result = _build_output_skeleton()
            result.update({
                "status": "insufficient_data",
                "valid_dept_count": valid_count,
                "missing_depts": missing_depts,
                "arbitration_method": "none",
                "arbitration_summary": (
                    f"有效部門僅 {valid_count} 個，不足以進行仲裁。"
                    f"缺失部門：{', '.join(missing_depts)}"
                ),
                "duration_ms": duration_ms,
            })
            return result

        # ── Step 2：信號對齊預掃描 ───────────────────────
        dept_signals = self._extract_signals(valid_outputs)
        alignment_summary = self._compute_alignment(dept_signals)

        # ── Step 3：呼叫 Gemini 仲裁 ─────────────────────
        gemini_result = self._call_gemini_arbitration(
            valid_outputs, missing_depts, alignment_summary, report_id
        )

        duration_ms = int((time.time() - start) * 1000)

        if gemini_result is not None:
            # Gemini 成功 -> 補全 + 回傳
            output = self._finalize_output(
                gemini_result, valid_count, missing_depts,
                "gemini", duration_ms,
            )
            log_agent_action(
                self.agent_name, report_id, "success",
                action="arbitrate", duration_ms=duration_ms,
                metadata={"method": "gemini", "stance": output.get("final_stance")},
            )
            return output

        # ── Step 4：Gemini 失敗 -> 規則引擎降級 ──────────
        logger.warning("[Arbitrator] Gemini 仲裁失敗，啟用規則引擎降級")
        rule_result = self._rule_based_arbitration(dept_signals)
        output = self._finalize_output(
            rule_result, valid_count, missing_depts,
            "rule_based", duration_ms,
        )

        log_agent_action(
            self.agent_name, report_id, "success",
            action="arbitrate_rule_based", duration_ms=duration_ms,
            metadata={"method": "rule_based", "stance": output.get("final_stance")},
        )
        return output

    # ── 前處理 ──────────────────────────────────────────────

    def _preprocess_depts(
        self, raw_depts: dict[str, dict]
    ) -> tuple[dict[str, Any], list[str]]:
        """
        將六部門輸出分為「有效」和「缺失」。

        有效條件：
        - status 不是 "rate_limited" 或 "failed"（或雖失敗但有 output 文字）
        - parse_failed=True 但有 raw 文字仍可用
        - 含有任何已知的部門特徵欄位（trend, growth, institutional 等）

        Returns:
            (valid_outputs, missing_dept_names)
        """
        valid = {}
        missing = []

        # 各部門可能出現的特徵欄位（用於判斷是否有實質內容）
        _content_fields = (
            "summary", "raw", "trend", "growth", "institutional",
            "earnings", "us_markets", "social_media", "direction",
            "stance", "signal", "outlook", "confidence", "conclusion",
            "catalyst_score", "macro_impact_on_target", "contrarian_signal",
            "valuation", "overall_signal", "support_levels", "resistance_levels",
        )

        for dept_name, output in raw_depts.items():
            if not isinstance(output, dict):
                missing.append(dept_name)
                continue

            status = output.get("status")

            # 明確失敗或 rate limited
            if status in ("rate_limited", "failed"):
                # 檢查是否有任何可用內容
                has_content = (
                    output.get("output")
                    or any(output.get(f) for f in _content_fields)
                )
                if has_content:
                    # 有內容就保留，標記 parse_failed
                    if output.get("output"):
                        valid[dept_name] = {
                            "raw": output["output"], "parse_failed": True
                        }
                    else:
                        valid[dept_name] = output
                else:
                    missing.append(dept_name)
                continue

            # parse_failed 但有 raw -> 仍可用
            if output.get("parse_failed") and output.get("raw"):
                valid[dept_name] = output
                continue

            # 正常結構化輸出（或至少有些欄位）
            valid[dept_name] = output

        return valid, missing

    # ── 信號提取 ────────────────────────────────────────────

    def _extract_signals(
        self, valid_outputs: dict[str, dict]
    ) -> dict[str, str]:
        """
        從各部門輸出中擷取核心信號方向。

        嘗試策略（按優先序）：
        1. 部門專屬欄位（如 technical 的 trend, chips 的 institutional.overall）
        2. 通用方向欄位（trend, direction, stance, signal, outlook）
        3. 從 summary / conclusion 文字推斷
        4. 從 confidence 數值推斷

        Returns:
            {dept_name: "bullish"|"bearish"|"neutral"|"cautious_bullish"|"cautious_bearish"|"unknown"}
        """
        signals = {}

        for dept_name, output in valid_outputs.items():
            if output.get("parse_failed"):
                signals[dept_name] = self._infer_signal_from_text(
                    output.get("raw", "")
                )
                continue

            # 先嘗試部門專屬邏輯
            dept_signal = self._extract_dept_specific_signal(dept_name, output)
            if dept_signal != "unknown":
                signals[dept_name] = dept_signal
                continue

            # 通用欄位提取
            generic_signal = self._extract_generic_signal(output)
            signals[dept_name] = generic_signal

        return signals

    def _extract_dept_specific_signal(self, dept_name: str, output: dict) -> str:
        """嘗試用部門專屬邏輯提取信號。"""

        if dept_name == "technical":
            trend = output.get("trend")
            if isinstance(trend, str):
                return self._normalize_signal(trend)

        elif dept_name == "fundamental":
            # 嘗試 valuation.overall_valuation
            valuation = output.get("valuation", {})
            if isinstance(valuation, dict):
                overall = valuation.get("overall_valuation", "")
                if "undervalued" in str(overall).lower():
                    return "bullish"
                if "overvalued" in str(overall).lower():
                    return "bearish"
                if "fairly" in str(overall).lower():
                    return "neutral"
            # 嘗試 growth 欄位
            growth = output.get("growth", {})
            if isinstance(growth, dict):
                eps_growth = growth.get("eps_yoy")
                if isinstance(eps_growth, (int, float)):
                    if eps_growth > 15:
                        return "bullish"
                    if eps_growth < -10:
                        return "bearish"
                    return "neutral"

        elif dept_name == "chips":
            inst = output.get("institutional", {})
            if isinstance(inst, dict):
                overall = str(inst.get("overall", "")).lower()
                if "buying" in overall or "buy" in overall:
                    return "bullish"
                if "selling" in overall or "sell" in overall:
                    return "bearish"
                if overall:
                    return "neutral"

        elif dept_name == "event":
            score = output.get("catalyst_score")
            if isinstance(score, (int, float)):
                if score > 1:
                    return "bullish"
                if score < -1:
                    return "bearish"
                return "neutral"

        elif dept_name == "macro":
            impact = output.get("macro_impact_on_target", "")
            if isinstance(impact, str):
                impact_l = impact.lower()
                if impact_l in ("tailwind", "bullish", "positive"):
                    return "bullish"
                if impact_l in ("headwind", "bearish", "negative"):
                    return "bearish"
                if impact_l:
                    return "neutral"

        elif dept_name == "sentiment":
            contrarian = output.get("contrarian_signal", "")
            if isinstance(contrarian, str):
                cl = contrarian.lower()
                if "buy" in cl or "bullish" in cl:
                    return "bullish"
                if "sell" in cl or "bearish" in cl:
                    return "bearish"
                if cl:
                    return "neutral"

        return "unknown"

    def _extract_generic_signal(self, output: dict) -> str:
        """從通用結構化欄位提取信號方向。"""
        # 嘗試多種常見欄位名
        candidate_fields = [
            "trend", "direction", "stance", "signal",
            "outlook", "overall_signal", "bias",
        ]

        for field in candidate_fields:
            value = output.get(field)
            if isinstance(value, str):
                normalized = self._normalize_signal(value)
                if normalized != "unknown":
                    return normalized

        # 嘗試從 summary / conclusion 欄位推斷
        for text_field in ("summary", "conclusion", "overall"):
            text = output.get(text_field)
            if isinstance(text, str) and len(text) > 5:
                return self._infer_signal_from_text(text)

        # 嘗試從 confidence 數值推斷
        confidence = output.get("confidence")
        if isinstance(confidence, (int, float)):
            if confidence > 0.65:
                return "cautious_bullish"
            if confidence < 0.35:
                return "cautious_bearish"

        return "unknown"

    @staticmethod
    def _normalize_signal(value: str) -> str:
        """將各種表述正規化為標準信號。"""
        v = value.strip().lower().replace(" ", "_").replace("-", "_")

        bullish_terms = {
            "bullish", "long", "buy", "overweight", "positive",
            "strong_buy", "accumulate", "uptrend", "up",
        }
        cautious_bullish_terms = {
            "cautious_bullish", "slightly_bullish", "mild_bullish",
            "weak_bullish", "lean_long",
        }
        bearish_terms = {
            "bearish", "short", "sell", "underweight", "negative",
            "strong_sell", "reduce", "downtrend", "down",
        }
        cautious_bearish_terms = {
            "cautious_bearish", "slightly_bearish", "mild_bearish",
            "weak_bearish", "lean_short",
        }
        neutral_terms = {
            "neutral", "hold", "sideways", "range", "consolidation",
            "mixed", "flat",
        }

        if v in bullish_terms:
            return "bullish"
        if v in cautious_bullish_terms:
            return "cautious_bullish"
        if v in bearish_terms:
            return "bearish"
        if v in cautious_bearish_terms:
            return "cautious_bearish"
        if v in neutral_terms:
            return "neutral"

        # 部分匹配（順序重要：先匹配帶修飾詞的）
        if "cautious_bullish" in v:
            return "cautious_bullish"
        if "cautious_bearish" in v:
            return "cautious_bearish"
        if "bullish" in v or "buy" in v or "long" in v:
            return "bullish"
        if "bearish" in v or "sell" in v or "short" in v:
            return "bearish"
        if "neutral" in v or "hold" in v or "sideways" in v:
            return "neutral"

        return "unknown"

    @staticmethod
    def _infer_signal_from_text(text: str) -> str:
        """從自由文字推斷信號方向（簡易關鍵字統計）。"""
        if not text:
            return "unknown"

        text_lower = text.lower()

        bullish_keywords = [
            "多頭", "看多", "bullish", "買進", "上漲", "突破",
            "利多", "加碼", "偏多", "強勢", "上升趨勢", "做多",
            "翻多", "站穩", "創高",
        ]
        bearish_keywords = [
            "空頭", "看空", "bearish", "賣出", "下跌", "跌破",
            "利空", "減碼", "偏空", "弱勢", "下降趨勢", "做空",
            "翻空", "破底", "崩跌",
        ]

        bull_count = sum(1 for kw in bullish_keywords if kw in text_lower)
        bear_count = sum(1 for kw in bearish_keywords if kw in text_lower)

        if bull_count > bear_count + 1:
            return "bullish"
        if bear_count > bull_count + 1:
            return "bearish"
        if bull_count > 0 and bear_count > 0:
            return "neutral"
        if bull_count > 0:
            return "cautious_bullish"
        if bear_count > 0:
            return "cautious_bearish"

        return "unknown"

    # ── 一致性計算 ──────────────────────────────────────────

    @staticmethod
    def _compute_alignment(dept_signals: dict[str, str]) -> str:
        """
        計算信號一致性摘要，附加到 Gemini prompt 中。

        Returns:
            人類可讀的一致性描述（繁中），約 2-5 行
        """
        bullish_depts = []
        bearish_depts = []
        neutral_depts = []
        unknown_depts = []

        for dept, signal in dept_signals.items():
            if signal in ("bullish", "cautious_bullish"):
                bullish_depts.append(f"{dept}({signal})")
            elif signal in ("bearish", "cautious_bearish"):
                bearish_depts.append(f"{dept}({signal})")
            elif signal == "neutral":
                neutral_depts.append(dept)
            else:
                unknown_depts.append(dept)

        total_known = len(bullish_depts) + len(bearish_depts) + len(neutral_depts)
        if total_known == 0:
            return "無法從部門輸出中提取明確信號。"

        lines = ["## 信號對齊預掃描結果"]

        if bullish_depts:
            lines.append(
                f"- 偏多陣營（{len(bullish_depts)}）：{', '.join(bullish_depts)}"
            )
        if bearish_depts:
            lines.append(
                f"- 偏空陣營（{len(bearish_depts)}）：{', '.join(bearish_depts)}"
            )
        if neutral_depts:
            lines.append(
                f"- 中性（{len(neutral_depts)}）：{', '.join(neutral_depts)}"
            )
        if unknown_depts:
            lines.append(
                f"- 無法判斷（{len(unknown_depts)}）：{', '.join(unknown_depts)}"
            )

        # 一致性分數
        dominant = max(len(bullish_depts), len(bearish_depts), len(neutral_depts))
        consistency = dominant / total_known
        lines.append(f"- 一致性分數：{consistency:.0%}（最大陣營佔比）")

        return "\n".join(lines)

    # ── Gemini 仲裁 ─────────────────────────────────────────

    def _call_gemini_arbitration(
        self,
        valid_outputs: dict[str, dict],
        missing_depts: list[str],
        alignment_summary: str,
        report_id: Optional[str],
    ) -> Optional[dict]:
        """
        呼叫 Gemini 執行仲裁。

        Returns:
            解析後的仲裁結果 dict，或 None（Gemini 完全失敗時）
        """
        # 準備各部門輸出文字（限制長度避免超過 token limit）
        dept_texts = {}
        for dept_name in DEPARTMENT_NAMES:
            if dept_name in valid_outputs:
                output = valid_outputs[dept_name]
                if output.get("parse_failed"):
                    raw = output.get("raw", "無資料")
                    dept_texts[dept_name] = (
                        f"[原始文字，JSON 解析失敗]\n{_truncate(raw, _MAX_DEPT_CHARS)}"
                    )
                else:
                    serialized = json.dumps(output, ensure_ascii=False, indent=2)
                    dept_texts[dept_name] = _truncate(serialized, _MAX_DEPT_CHARS)
            else:
                dept_texts[dept_name] = "[此部門分析失敗，無可用資料]"

        # 透過 BaseAgent.run() 走統一 provider / budget / model routing
        result = self.run(
            report_id=report_id,
            technical_output=dept_texts["technical"],
            fundamental_output=dept_texts["fundamental"],
            chips_output=dept_texts["chips"],
            event_output=dept_texts["event"],
            macro_output=dept_texts["macro"],
            sentiment_output=dept_texts["sentiment"],
            alignment_summary=alignment_summary,
            missing_departments=", ".join(missing_depts) if missing_depts else "無",
            extra_instructions=(
                "有部門缺失時，必須明確降低信心並把缺失列入 key_risks。"
                if missing_depts else
                "請以證據權重做裁決，不要採用多數決。"
            ),
        )

        if result["status"] != "success" or not result.get("output"):
            logger.warning(
                f"[Arbitrator] Gemini 呼叫 {result['status']}: "
                f"{result.get('error', 'no output')}"
            )
            return None

        # 解析 Gemini 輸出
        parsed = self._parse_gemini_output(result["output"])
        if parsed is None:
            return None

        # 附加模型資訊
        parsed["model_used"] = result.get("model_used", "unknown")
        return parsed

    def _parse_gemini_output(self, text: str) -> Optional[dict]:
        """
        解析 Gemini 仲裁輸出。

        策略（按順序嘗試）：
        1. 直接 JSON parse（清除 markdown code block）
        2. 用 regex 提取最外層 JSON block
        3. 逐欄位 regex 提取關鍵欄位

        Returns:
            解析後的 dict，或 None
        """
        if not text:
            return None

        # ── 嘗試 1：直接 JSON parse ──────────────────────
        cleaned = _strip_markdown_fence(text)
        try:
            parsed = json.loads(cleaned)
            if isinstance(parsed, dict):
                return self._sanitize_parsed(parsed)
        except (json.JSONDecodeError, ValueError):
            pass

        # ── 嘗試 2：regex 提取 JSON block ────────────────
        #    找最外層 { ... }，使用貪婪匹配
        json_match = re.search(r'\{[\s\S]*\}', text)
        if json_match:
            try:
                parsed = json.loads(json_match.group())
                if isinstance(parsed, dict):
                    return self._sanitize_parsed(parsed)
            except json.JSONDecodeError:
                pass

        # ── 嘗試 3：逐欄位 regex 提取 ────────────────────
        logger.warning(
            "[Arbitrator] JSON 完整解析失敗，嘗試 regex 逐欄位提取"
        )
        extracted = self._regex_extract_fields(text)
        if extracted.get("final_stance") in VALID_STANCES:
            return self._sanitize_parsed(extracted)

        logger.error("[Arbitrator] Gemini 輸出完全無法解析")
        return None

    def _sanitize_parsed(self, parsed: dict) -> dict:
        """
        清理並驗證 Gemini 解析結果。

        - 驗證 final_stance 是否合法
        - 驗證 stance_confidence 在 0~1
        - 確保必要欄位存在
        """
        # final_stance
        stance = parsed.get("final_stance", "neutral")
        if stance not in VALID_STANCES:
            logger.warning(
                f"[Arbitrator] 非法 final_stance '{stance}'，修正為 neutral"
            )
            parsed["final_stance"] = "neutral"

        # stance_confidence
        try:
            conf = float(parsed.get("stance_confidence", 0.5))
            parsed["stance_confidence"] = max(0.0, min(1.0, conf))
        except (TypeError, ValueError):
            parsed["stance_confidence"] = 0.5

        # 確保 list 欄位
        for list_key in (
            "conflicts_detected", "aligned_signals",
            "aligned_bearish_signals", "key_risks", "key_catalysts",
        ):
            val = parsed.get(list_key)
            if not isinstance(val, list):
                parsed[list_key] = [] if val is None else [str(val)]

        # 確保 arbitration_summary 是字串
        summary = parsed.get("arbitration_summary")
        if not isinstance(summary, str):
            parsed["arbitration_summary"] = str(summary) if summary else ""

        return parsed

    @staticmethod
    def _regex_extract_fields(text: str) -> dict:
        """
        最後手段：用 regex 從雜亂文字中提取關鍵欄位。
        """
        result: dict[str, Any] = {}

        # final_stance
        stance_match = re.search(
            r'"final_stance"\s*:\s*"(bullish|cautious_bullish|neutral'
            r'|cautious_bearish|bearish)"',
            text,
        )
        if stance_match:
            result["final_stance"] = stance_match.group(1)

        # stance_confidence
        conf_match = re.search(
            r'"stance_confidence"\s*:\s*([\d.]+)', text
        )
        if conf_match:
            try:
                result["stance_confidence"] = float(conf_match.group(1))
            except ValueError:
                pass

        # arbitration_summary
        summary_match = re.search(
            r'"arbitration_summary"\s*:\s*"([^"]{10,500})"', text
        )
        if summary_match:
            result["arbitration_summary"] = summary_match.group(1)

        # key_risks
        risks_match = re.search(
            r'"key_risks"\s*:\s*\[(.*?)\]', text, re.DOTALL
        )
        if risks_match:
            try:
                result["key_risks"] = json.loads("[" + risks_match.group(1) + "]")
            except json.JSONDecodeError:
                result["key_risks"] = re.findall(
                    r'"([^"]+)"', risks_match.group(1)
                )

        # key_catalysts
        catalysts_match = re.search(
            r'"key_catalysts"\s*:\s*\[(.*?)\]', text, re.DOTALL
        )
        if catalysts_match:
            try:
                result["key_catalysts"] = json.loads(
                    "[" + catalysts_match.group(1) + "]"
                )
            except json.JSONDecodeError:
                result["key_catalysts"] = re.findall(
                    r'"([^"]+)"', catalysts_match.group(1)
                )

        return result

    # ── 規則引擎降級 ────────────────────────────────────────

    def _rule_based_arbitration(self, dept_signals: dict[str, str]) -> dict:
        """
        當 Gemini 呼叫失敗時的規則引擎仲裁。

        計分規則：
        - bullish=+1, cautious_bullish=+0.5, neutral=0,
          cautious_bearish=-0.5, bearish=-1, unknown=0(不計入加權)

        加權：technical=1.0, fundamental=1.2, chips=1.3,
              event=1.1, macro=0.9, sentiment=0.8

        最終分數 -> 立場：
        - > +0.8：bullish
        - +0.3 ~ +0.8：cautious_bullish
        - -0.3 ~ +0.3：neutral
        - -0.8 ~ -0.3：cautious_bearish
        - < -0.8：bearish
        """
        weighted_sum = 0.0
        total_weight = 0.0
        bullish_depts = []
        bearish_depts = []

        for dept_name, signal in dept_signals.items():
            score = _SIGNAL_SCORE.get(signal)
            if score is None:
                # unknown -> 不計入加權
                continue

            weight = _DEPT_WEIGHT.get(dept_name, 1.0)
            weighted_sum += score * weight
            total_weight += weight

            agent_name = _DEPT_AGENT_NAME.get(dept_name, dept_name)
            if signal in ("bullish", "cautious_bullish"):
                bullish_depts.append(agent_name)
            elif signal in ("bearish", "cautious_bearish"):
                bearish_depts.append(agent_name)

        # 計算加權平均分數
        if total_weight > 0:
            final_score = weighted_sum / total_weight
        else:
            final_score = 0.0

        # 分數 -> 立場
        final_stance = _score_to_stance(final_score)

        # 信心基於信號一致性
        known_count = sum(
            1 for s in dept_signals.values() if s != "unknown"
        )
        if known_count > 0:
            dominant_count = max(
                len(bullish_depts), len(bearish_depts),
                known_count - len(bullish_depts) - len(bearish_depts),
            )
            confidence = round(
                min(0.85, 0.3 + (dominant_count / known_count) * 0.5), 2
            )
        else:
            confidence = 0.3

        # 找出潛在矛盾（多空對立的部門）
        conflicts = []
        if bullish_depts and bearish_depts:
            conflicts.append({
                "between": [bullish_depts[0], bearish_depts[0]],
                "conflict": "部門信號方向相反（規則引擎偵測）",
                "adopted": (
                    bullish_depts[0] if final_score > 0 else bearish_depts[0]
                ),
                "reason": "規則引擎依加權多數決採信",
                "confidence": confidence,
            })

        # 生成摘要
        signal_desc = ", ".join(
            f"{d}={s}" for d, s in dept_signals.items() if s != "unknown"
        )
        summary = (
            f"規則引擎仲裁（Gemini 不可用）。"
            f"加權分數 {final_score:+.2f}，判定 {final_stance}。"
            f"各部門信號：{signal_desc}。"
        )
        # 截至 200 字
        if len(summary) > 200:
            summary = summary[:197] + "..."

        return {
            "conflicts_detected": conflicts,
            "aligned_signals": bullish_depts,
            "aligned_bearish_signals": bearish_depts,
            "final_stance": final_stance,
            "stance_confidence": confidence,
            "key_risks": ["規則引擎仲裁精度有限，建議稍後重新分析"],
            "key_catalysts": [],
            "arbitration_summary": summary,
            "model_used": "rule_engine",
        }

    # ── 輸出最終化 ──────────────────────────────────────────

    @staticmethod
    def _finalize_output(
        parsed: dict,
        valid_dept_count: int,
        missing_depts: list[str],
        method: str,
        duration_ms: int,
    ) -> dict:
        """
        合併解析結果與 metadata，補全所有缺失欄位。

        保證回傳的 dict 永遠包含完整欄位結構。
        """
        skeleton = _build_output_skeleton()

        # 用 parsed 的值覆蓋 skeleton（僅非 None 的值）
        for key in skeleton:
            if key in parsed and parsed[key] is not None:
                skeleton[key] = parsed[key]

        # 強制設定 metadata 欄位
        skeleton["status"] = "success"
        skeleton["valid_dept_count"] = valid_dept_count
        skeleton["missing_depts"] = missing_depts
        skeleton["arbitration_method"] = method
        skeleton["duration_ms"] = duration_ms
        skeleton["model_used"] = parsed.get("model_used", "unknown")

        # 最終驗證 final_stance
        if skeleton["final_stance"] not in VALID_STANCES:
            logger.warning(
                f"[Arbitrator] 最終化時發現非法 final_stance: "
                f"{skeleton['final_stance']}，修正為 neutral"
            )
            skeleton["final_stance"] = "neutral"

        # 最終驗證 stance_confidence
        conf = skeleton["stance_confidence"]
        if not isinstance(conf, (int, float)) or conf < 0 or conf > 1:
            skeleton["stance_confidence"] = 0.5

        # 確保所有 list 欄位確實是 list
        for list_field in (
            "conflicts_detected", "aligned_signals",
            "aligned_bearish_signals", "key_risks", "key_catalysts",
            "missing_depts",
        ):
            if not isinstance(skeleton[list_field], list):
                skeleton[list_field] = []

        return skeleton


# ─── 模組級輔助函式 ────────────────────────────────────────────

def _build_output_skeleton() -> dict:
    """
    建立完整的輸出 dict 骨架，所有欄位都有合理預設值。
    上層程式碼可以安全地存取任何欄位。
    """
    return {
        "status": "failed",
        "conflicts_detected": [],
        "aligned_signals": [],
        "aligned_bearish_signals": [],
        "final_stance": "neutral",
        "stance_confidence": 0.5,
        "key_risks": [],
        "key_catalysts": [],
        "arbitration_summary": "",
        "arbitration_method": "none",
        "valid_dept_count": 0,
        "missing_depts": [],
        "model_used": "none",
        "duration_ms": 0,
    }


def _score_to_stance(score: float) -> str:
    """加權分數 -> 立場。"""
    if score > 0.8:
        return "bullish"
    if score > 0.3:
        return "cautious_bullish"
    if score > -0.3:
        return "neutral"
    if score > -0.8:
        return "cautious_bearish"
    return "bearish"


def _strip_markdown_fence(text: str) -> str:
    """移除 markdown code fence（```json ... ```）。"""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        start = 1
        end = len(lines)
        if lines[-1].strip() == "```":
            end = -1
        text = "\n".join(lines[start:end])
    return text.strip()


def _truncate(text: str, max_chars: int) -> str:
    """截斷文字到指定長度，超過時加省略號。"""
    if len(text) <= max_chars:
        return text
    return text[:max_chars - 3] + "..."
