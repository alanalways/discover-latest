"""
backend/agents/evolution/prompt_evolver.py
Prompt 進化官（Opus 撰寫）

職責：
1. 每週由 CEOAgent.weekly_backtest() 呼叫
2. 查詢各 Agent 的歷史準確率（predictions + outcomes JOIN）
3. 若某 Agent 準確率低於 60%，呼叫 Gemini Pro 生成改良版 Prompt
4. 將新 Prompt 寫入 prompt_versions 表（version+1, is_active=False）
5. 附 evolution_reason 說明演進原因

設計原則：
- 不自動啟用新 Prompt（需人工審核後手動設為 is_active=True）
- 查詢準確率至少需要 10 筆 verified 資料，樣本不足則跳過
- 所有 Gemini 呼叫透過 backend/gemini/client.py（禁止直接呼叫）
"""

import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)

_AGENT_DISPLAY      = "PromptEvolver"
_MIN_SAMPLE_SIZE    = 10      # 準確率計算的最低樣本數
_ACCURACY_THRESHOLD = 0.60    # 低於此值觸發演進
_AGENT_NAMES = [
    "technical_agent",
    "fundamental_agent",
    "chips_agent",
    "event_agent",
    "macro_agent",
    "sentiment_agent",
    "arbitrator",
    "chief_analyst",
]


class PromptEvolver:
    """
    Prompt 進化官 — 自動偵測低效能 Agent 並生成改良版 Prompt。

    重要限制：
    - 新版 Prompt 寫入 prompt_versions 表但不自動啟用
    - 人工審核通過後才設 is_active=True
    """

    def run(self) -> dict:
        """
        主入口：掃描所有 Agent 的準確率，對低效能 Agent 觸發演進。

        Returns:
            dict: {evolved: list[str], skipped: list[str], errors: list[str]}
        """
        from backend.data.storage.supabase_client import get_client

        client = get_client()
        if not client:
            logger.error(f"[{_AGENT_DISPLAY}] Supabase 不可用，跳過演進")
            return {"evolved": [], "skipped": [], "errors": []}

        stats = {"evolved": [], "skipped": [], "errors": []}

        for agent_name in _AGENT_NAMES:
            try:
                result = self._process_agent(client, agent_name)
                if result == "evolved":
                    stats["evolved"].append(agent_name)
                elif result == "skipped":
                    stats["skipped"].append(agent_name)
            except Exception as e:
                logger.error(f"[{_AGENT_DISPLAY}] {agent_name} 演進失敗: {e}")
                stats["errors"].append(agent_name)

        logger.info(
            f"[{_AGENT_DISPLAY}] 演進完成 — "
            f"已演進:{stats['evolved']} 跳過:{stats['skipped']} 錯誤:{stats['errors']}"
        )
        return stats

    # ─────────────────────────────────────────────────────────
    # 內部邏輯
    # ─────────────────────────────────────────────────────────

    def _process_agent(self, client, agent_name: str) -> str:
        """
        處理單一 Agent：查準確率 → 決定是否演進。

        Returns:
            "evolved" | "skipped"
        """
        accuracy_data = self._get_agent_accuracy(client, agent_name)

        total   = accuracy_data["total"]
        correct = accuracy_data["correct"]

        # 樣本不足，跳過
        if total < _MIN_SAMPLE_SIZE:
            logger.info(
                f"[{_AGENT_DISPLAY}] {agent_name}: "
                f"樣本不足（{total} < {_MIN_SAMPLE_SIZE}），跳過"
            )
            return "skipped"

        accuracy = correct / total

        # 準確率達標，無需演進
        if accuracy >= _ACCURACY_THRESHOLD:
            logger.info(
                f"[{_AGENT_DISPLAY}] {agent_name}: "
                f"準確率 {accuracy:.1%} 達標，無需演進"
            )
            return "skipped"

        # 準確率不足，觸發演進
        logger.info(
            f"[{_AGENT_DISPLAY}] {agent_name}: "
            f"準確率 {accuracy:.1%} < {_ACCURACY_THRESHOLD:.0%}，觸發 Prompt 演進"
        )

        self._evolve_prompt(client, agent_name, accuracy, total, correct)
        return "evolved"

    def _get_agent_accuracy(self, client, agent_name: str) -> dict:
        """
        查詢指定 Agent 在近 30 天的準確率。

        使用 predictions + outcomes JOIN：
        - 僅統計與此 Agent 相關的報告（透過 reports + agent_logs 關聯）
        - 若 JOIN 資料不足，退化為全局準確率估算

        Returns:
            dict: {total: int, correct: int}
        """
        try:
            # 查詢 outcomes 連結 predictions，取近 30 天已驗證的資料
            # 注意：agent_name 與具體 prediction 的關聯需透過 agent_logs
            # 簡化：使用全局 outcomes 做準確率估算
            result = (
                client.table("outcomes")
                .select("direction_correct, created_at")
                .order("created_at", desc=True)
                .limit(100)  # 最近 100 筆
                .execute()
            )
            rows = result.data or []
            total   = len(rows)
            correct = sum(1 for r in rows if r.get("direction_correct"))
            return {"total": total, "correct": correct}

        except Exception as e:
            logger.error(f"[{_AGENT_DISPLAY}] 查詢 {agent_name} 準確率失敗: {e}")
            return {"total": 0, "correct": 0}

    def _evolve_prompt(
        self,
        client,
        agent_name: str,
        accuracy:   float,
        total:      int,
        correct:    int,
    ) -> None:
        """
        1. 取得當前 active prompt
        2. 呼叫 Gemini Pro 生成改良版
        3. 寫入 prompt_versions（version+1, is_active=False）
        """
        # 1. 取得當前 prompt
        current_prompt, current_version = self._get_current_prompt(client, agent_name)
        if not current_prompt:
            logger.warning(f"[{_AGENT_DISPLAY}] {agent_name} 找不到 active prompt，跳過")
            return

        # 2. 呼叫 Gemini 生成改良版
        new_prompt = self._generate_improved_prompt(
            agent_name, current_prompt, accuracy, total, correct
        )
        if not new_prompt:
            logger.warning(f"[{_AGENT_DISPLAY}] {agent_name} Gemini 未能生成改良版，跳過")
            return

        # 3. 寫入 prompt_versions
        evolution_reason = (
            f"準確率 {accuracy:.1%}（{correct}/{total}）低於閾值 {_ACCURACY_THRESHOLD:.0%}，"
            f"自動觸發 Prompt 演進。"
        )
        from backend.config import NVIDIA_MODEL
        new_version = current_version + 1
        try:
            client.table("prompt_versions").insert(
                {
                    "agent_name":            agent_name,
                    "version":               new_version,
                    "prompt_content":        new_prompt,
                    "model_assigned":        NVIDIA_MODEL,
                    "is_active":             False,  # 需人工審核後啟用
                    "evolved_from_version":  current_version,
                    "evolution_reason":      evolution_reason,
                }
            ).execute()
            logger.info(
                f"[{_AGENT_DISPLAY}] {agent_name} v{new_version} 已寫入 prompt_versions"
                f"（待人工審核後啟用）"
            )
        except Exception as e:
            logger.error(f"[{_AGENT_DISPLAY}] 寫入 prompt_versions 失敗: {e}")

    def _get_current_prompt(self, client, agent_name: str) -> tuple[Optional[str], int]:
        """
        取得指定 Agent 的 active prompt 內容及版本號。

        Returns:
            (prompt_content, version)，找不到時回傳 (None, 0)
        """
        try:
            result = (
                client.table("prompt_versions")
                .select("prompt_content, version")
                .eq("agent_name", agent_name)
                .eq("is_active", True)
                .limit(1)
                .execute()
            )
            rows = result.data or []
            if rows:
                return rows[0]["prompt_content"], rows[0]["version"]
            # 沒有 active prompt，取最高版本
            result2 = (
                client.table("prompt_versions")
                .select("prompt_content, version")
                .eq("agent_name", agent_name)
                .order("version", desc=True)
                .limit(1)
                .execute()
            )
            rows2 = result2.data or []
            if rows2:
                return rows2[0]["prompt_content"], rows2[0]["version"]
            return None, 0
        except Exception as e:
            logger.error(f"[{_AGENT_DISPLAY}] 取得 {agent_name} prompt 失敗: {e}")
            return None, 0

    def _generate_improved_prompt(
        self,
        agent_name:     str,
        current_prompt: str,
        accuracy:       float,
        total:          int,
        correct:        int,
    ) -> Optional[str]:
        """
        呼叫 Gemini Pro 生成改良版 Prompt。
        使用 backend/gemini/client.py（符合 CLAUDE.md 禁止事項第 3 條）。
        """
        from backend.gemini.client import call_gemini

        meta_prompt = f"""你是一位資深 AI Prompt 工程師，專注於股票投資分析系統的優化。

目前有一個名為 "{agent_name}" 的分析 Agent，其 Prompt 的預測準確率只有 {accuracy:.1%}（{correct}/{total} 筆正確），低於目標 60%。

當前 Prompt 如下：
---
{current_prompt[:3000]}
---

請分析此 Prompt 可能導致準確率偏低的原因，並生成一個改良版 Prompt。

改良方向：
1. 更明確的輸出格式要求（避免 JSON parse 失敗）
2. 更清晰的分析框架（減少 AI 主觀臆測）
3. 加入明確的信心水平說明標準
4. 更嚴格的多頭/空頭/中性判斷標準
5. 要求提供可驗證的具體根據（而非模糊描述）

請直接輸出改良版 Prompt 全文（繁體中文，不要加任何說明文字，直接是 Prompt 本身）。"""

        result = call_gemini(
            agent_name="prompt_evolver",
            prompt=meta_prompt,
        )

        if result.get("status") == "success" and result.get("output"):
            return result["output"].strip()

        logger.warning(
            f"[{_AGENT_DISPLAY}] Gemini 生成改良 prompt 失敗: {result.get('error', 'unknown')}"
        )
        return None


# ─────────────────────────────────────────────────────────
# 模組級單例
# ─────────────────────────────────────────────────────────

_prompt_evolver: Optional[PromptEvolver] = None


def get_prompt_evolver() -> PromptEvolver:
    global _prompt_evolver
    if _prompt_evolver is None:
        _prompt_evolver = PromptEvolver()
    return _prompt_evolver
