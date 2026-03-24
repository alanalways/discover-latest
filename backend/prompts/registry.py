"""
backend/prompts/registry.py
Prompt 版本控制登錄表
- 管理所有 Agent 的 active prompt
- 優先從 Supabase prompt_versions 表讀取
- 降級為本地 v1 定義（確保離線也可運作）
"""
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# ── 本地 Prompt 定義（v1 預設）──────────────────────────
from backend.prompts.v1.technical import TECHNICAL_PROMPT_V1
from backend.prompts.v1.fundamental import FUNDAMENTAL_PROMPT_V1
from backend.prompts.v1.chips import CHIPS_PROMPT_V1
from backend.prompts.v1.event import EVENT_PROMPT_V1
from backend.prompts.v1.macro import MACRO_PROMPT_V1
from backend.prompts.v1.sentiment import SENTIMENT_PROMPT_V1
from backend.prompts.v1.arbitrator import ARBITRATOR_PROMPT_V1
from backend.prompts.v1.chief_analyst import CHIEF_ANALYST_PROMPT_V1

# ── 本地 Prompt 版本登錄（agent_name → prompt_template）─
_LOCAL_PROMPTS: dict[str, str] = {
    "technical_agent":   TECHNICAL_PROMPT_V1,
    "fundamental_agent": FUNDAMENTAL_PROMPT_V1,
    "chips_agent":       CHIPS_PROMPT_V1,
    "event_agent":       EVENT_PROMPT_V1,
    "macro_agent":       MACRO_PROMPT_V1,
    "sentiment_agent":   SENTIMENT_PROMPT_V1,
    "arbitrator":        ARBITRATOR_PROMPT_V1,
    "chief_analyst":     CHIEF_ANALYST_PROMPT_V1,
}


def get_active_prompt(agent_name: str) -> str:
    """
    取得指定 agent 的目前 active prompt template。

    優先級：
    1. Supabase prompt_versions 表中 is_active=TRUE 的版本
    2. 降級：本地 v1 定義

    Returns:
        prompt template 字串（使用 str.format(**kwargs) 填入變數）
    """
    # 先嘗試從 Supabase 讀取最新 active prompt
    db_prompt = _load_from_db(agent_name)
    if db_prompt:
        return db_prompt

    # 降級：使用本地 v1
    local = _LOCAL_PROMPTS.get(agent_name)
    if local:
        logger.debug(f"[Registry] {agent_name} 使用本地 v1 prompt")
        return local

    raise ValueError(f"[Registry] 找不到 agent '{agent_name}' 的 prompt 定義")


def _load_from_db(agent_name: str) -> Optional[str]:
    """從 Supabase 讀取 is_active=TRUE 的 prompt（失敗回傳 None）。"""
    try:
        from backend.data.storage.supabase_client import get_client
        client = get_client()
        if not client:
            return None

        result = (
            client.table("prompt_versions")
            .select("prompt_content, version")
            .eq("agent_name", agent_name)
            .eq("is_active", True)
            .limit(1)
            .execute()
        )

        if result.data:
            row = result.data[0]
            logger.debug(
                f"[Registry] {agent_name} 使用 DB v{row['version']} prompt"
            )
            return row["prompt_content"]

        return None

    except Exception as e:
        logger.debug(f"[Registry] 無法從 DB 讀取 {agent_name} prompt: {e}")
        return None


def seed_initial_prompts() -> None:
    """
    將本地 v1 prompts 寫入 Supabase prompt_versions 表（初始化用）。
    若已存在則跳過。
    """
    try:
        from backend.data.storage.supabase_client import get_client
        from backend.config import AGENT_MODEL_MAP, NVIDIA_MODEL

        client = get_client()
        if not client:
            logger.warning("[Registry] Supabase 不可用，跳過 prompt seeding")
            return

        seeded = 0
        for agent_name, prompt_content in _LOCAL_PROMPTS.items():
            # 檢查是否已存在 v1
            existing = (
                client.table("prompt_versions")
                .select("id")
                .eq("agent_name", agent_name)
                .eq("version", 1)
                .execute()
            )
            if existing.data:
                continue

            client.table("prompt_versions").insert({
                "agent_name": agent_name,
                "version": 1,
                "prompt_content": prompt_content,
                "model_assigned": AGENT_MODEL_MAP.get(agent_name, NVIDIA_MODEL),
                "is_active": True,
            }).execute()
            seeded += 1

        if seeded:
            logger.info(f"[Registry] 已 seed {seeded} 個 v1 prompts 到 Supabase")

    except Exception as e:
        logger.error(f"[Registry] Prompt seeding 失敗: {e}")


def list_all_agents() -> list[str]:
    """回傳所有已知 agent 名稱清單。"""
    return list(_LOCAL_PROMPTS.keys())
