"""Financial news brief API.

Priority:
1) Tavily scheduled search (if keys exist)
2) Gemini grounding collection
3) RSS fallback

Output is cached for 30 minutes and includes:
- one_minute_brief (Traditional Chinese)
- brief bullets
- impact table
- source items
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import html
import json
import os
import re
import threading
from typing import Any
import xml.etree.ElementTree as ET

import httpx
from fastapi import APIRouter

router = APIRouter()

_NEWS_CACHE_TTL_SEC = 1800
_NEWS_CACHE: dict[str, Any] = {"ts": 0.0, "data": None}
_NEWS_LOCK = asyncio.Lock()

_TAVILY_KEYS: list[str] = []
_TAVILY_KEY_INDEX = 0
_TAVILY_LOCK = threading.Lock()

_RSS_SOURCES = [
    "https://news.google.com/rss/search?q=finance+stock+market+when:1d&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=%E8%B2%A1%E7%B6%93+%E8%82%A1%E5%B8%82+when:1d&hl=zh-TW&gl=TW&ceid=TW:zh-Hant",
]

_FALLBACK_BRIEF = [
    "全球市場短線聚焦利率路徑、企業財報與地緣政治三大主軸。",
    "台股與美股資金仍偏向大型權值與 AI 供應鏈，族群輪動速度加快。",
    "若即時來源短暫延遲，系統會先顯示上一版重點，避免畫面空白。",
]
_FALLBACK_ONE_MINUTE = (
    "一分鐘看市場：目前盤面由利率預期、財報結果與地緣風險共同主導，"
    "資金集中在權值與 AI 主軸，短線波動放大，建議先看風險控管再做追價。"
)

_TOPIC_QUERY_MAP = {
    "G1": "global macro economy interest rate inflation treasury yield USD TWD oil market impact latest 24h",
    "G2": "geopolitics war sanctions conflict supply chain market impact latest 24h",
    "T1": "Taiwan stock market sentiment unusual volatility TWSE TPEX latest today",
    "T2": "Taiwan AI supply chain TSMC MediaTek Hon Hai latest news",
    "T3": "Taiwan semiconductor AI industry trend latest developments",
    "U1": "US stock market sentiment futures S&P 500 Nasdaq latest",
    "U2": "US megacap tech AI Magnificent Seven earnings guidance latest",
}


def _taipei_now() -> datetime:
    return datetime.now(timezone.utc) + timedelta(hours=8)


def _is_weekday(dt: datetime) -> bool:
    return dt.weekday() < 5


def _scheduled_topic_keys(now_tw: datetime) -> tuple[str, list[str]]:
    """Return (session_tag, topic_keys) following the trading-session profile."""
    hhmm = now_tw.hour * 100 + now_tw.minute
    if not _is_weekday(now_tw):
        return "weekend", ["G1", "U1", "T1"]

    # Taiwan market windows
    if 830 <= hhmm < 900:
        return "tw_pre_open", ["G1", "G2", "T1", "T2", "T3", "U1"]
    if 900 <= hhmm < 930:
        return "tw_open_spike", ["T1", "T2"]
    if 930 <= hhmm < 1330:
        if 1200 <= hhmm < 1230:
            return "tw_mid_special", ["T1", "T3"]
        return "tw_intraday", ["T1", "T2", "T3"]
    if 1330 <= hhmm < 1400:
        return "tw_tail_special", ["T1", "T2"]
    if 1400 <= hhmm < 1430:
        return "tw_post_close", ["T1", "T2", "T3"]

    # US market windows (Taiwan time)
    if 2130 <= hhmm < 2200:
        return "us_pre_open", ["G1", "G2", "U1", "U2", "T1"]
    if hhmm >= 2230 or hhmm < 500:
        if 130 <= hhmm < 200:
            return "us_mid_special", ["U1", "U2"]
        return "us_intraday", ["U1", "U2"]
    if 530 <= hhmm < 600:
        return "us_post_close", ["U1", "U2"]

    return "off_session", ["G1", "T1", "U1"]


def _pick_gemini_key() -> str:
    multi = (os.environ.get("GEMINI_API_KEYS") or "").strip()
    if multi:
        keys = [k.strip() for k in multi.split(",") if k.strip()]
        if keys:
            return keys[0]
    return (os.environ.get("GEMINI_API_KEY") or "").strip()


def _load_tavily_keys() -> list[str]:
    global _TAVILY_KEYS
    if _TAVILY_KEYS:
        return _TAVILY_KEYS
    merged = []
    for env_name in ("TAVILY_API_KEYS", "TAVILY_API_KEY"):
        value = (os.environ.get(env_name) or "").strip()
        if not value:
            continue
        if env_name.endswith("KEYS"):
            merged.extend([v.strip() for v in value.split(",") if v.strip()])
        else:
            merged.append(value)

    dedup: list[str] = []
    seen = set()
    for key in merged:
        if key in seen:
            continue
        seen.add(key)
        dedup.append(key)
    _TAVILY_KEYS = dedup
    return _TAVILY_KEYS


def _next_tavily_key() -> str:
    global _TAVILY_KEY_INDEX
    keys = _load_tavily_keys()
    if not keys:
        return ""
    with _TAVILY_LOCK:
        key = keys[_TAVILY_KEY_INDEX % len(keys)]
        _TAVILY_KEY_INDEX += 1
    return key


def _extract_json_object(text: str) -> dict[str, Any]:
    if not text:
        return {}
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        parsed = json.loads(cleaned)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        pass

    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start >= 0 and end > start:
        try:
            parsed = json.loads(cleaned[start : end + 1])
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


def _normalize_items(items: Any, max_items: int = 12) -> list[dict[str, Any]]:
    if not isinstance(items, list):
        return []
    rows: list[dict[str, Any]] = []
    seen = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        url = str(item.get("url") or item.get("link") or "").strip()
        source = str(item.get("source") or "").strip()
        if not title or not url:
            continue
        key = f"{title.lower()}|{source.lower()}"
        if key in seen:
            continue
        seen.add(key)
        rows.append(
            {
                "title": title,
                "url": url,
                "source": source or "News",
                "published_at": str(item.get("published_at") or item.get("published") or "").strip(),
                "region": str(item.get("region") or "").strip(),
                "impact": str(item.get("impact") or item.get("impact_level") or "").strip(),
                "impact_reason": str(item.get("impact_reason") or "").strip(),
            }
        )
        if len(rows) >= max_items:
            break
    return rows


def _normalize_payload(payload: dict[str, Any], provider: str = "unknown", session_tag: str = "") -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    brief = payload.get("brief") if isinstance(payload, dict) else None
    items = payload.get("items") if isinstance(payload, dict) else None
    table = payload.get("table") if isinstance(payload, dict) else None
    one_minute = str(payload.get("one_minute_brief") or "").strip()

    norm_brief = [str(x).strip() for x in (brief or []) if str(x).strip()]
    if not norm_brief:
        norm_brief = list(_FALLBACK_BRIEF)

    norm_items = _normalize_items(items, max_items=12)
    norm_table = table if isinstance(table, list) else []
    if not one_minute:
        one_minute = "；".join(norm_brief[:2]) or _FALLBACK_ONE_MINUTE

    return {
        "updated_at": now.isoformat(),
        "next_update_at": (now + timedelta(seconds=_NEWS_CACHE_TTL_SEC)).isoformat(),
        "one_minute_brief": one_minute,
        "brief": norm_brief[:5],
        "items": norm_items,
        "table": norm_table[:8],
        "provider": provider,
        "session_tag": session_tag,
    }


def _strip_html(value: str) -> str:
    text = re.sub(r"<[^>]+>", " ", value or "")
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _parse_rss(xml_text: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        root = ET.fromstring(xml_text)
    except Exception:
        return rows

    for item in root.findall(".//item"):
        title = _strip_html(item.findtext("title") or "")
        link = (item.findtext("link") or "").strip()
        source = _strip_html(item.findtext("source") or "")
        pub = _strip_html(item.findtext("pubDate") or "")
        desc = _strip_html(item.findtext("description") or "")
        if not title or not link:
            continue
        rows.append(
            {
                "title": title,
                "url": link,
                "source": source or "News",
                "published_at": pub,
                "impact_reason": desc[:220],
                "impact": "",
                "region": "",
            }
        )
    return rows


async def _fetch_news_rss_fallback() -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    async with httpx.AsyncClient(timeout=12.0) as client:
        for url in _RSS_SOURCES:
            try:
                resp = await client.get(url, headers={"User-Agent": "DiscoverLatest-News/1.0"})
                if resp.is_success and resp.text:
                    rows.extend(_parse_rss(resp.text))
            except Exception:
                continue

    dedup: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = f"{row.get('title', '').strip().lower()}|{row.get('source', '').strip().lower()}"
        if key and key not in dedup:
            dedup[key] = row
    items = list(dedup.values())[:12]
    return _normalize_payload(
        {"one_minute_brief": _FALLBACK_ONE_MINUTE, "brief": _FALLBACK_BRIEF, "items": items, "table": []},
        provider="rss",
        session_tag="fallback",
    )


async def _collect_news_with_tavily() -> tuple[list[dict[str, Any]], str]:
    first_key = _next_tavily_key()
    if not first_key:
        raise RuntimeError("no_tavily_key")

    now_tw = _taipei_now()
    session_tag, topic_keys = _scheduled_topic_keys(now_tw)
    items: list[dict[str, Any]] = []

    async with httpx.AsyncClient(timeout=16.0) as client:
        for topic in topic_keys:
            query = _TOPIC_QUERY_MAP.get(topic)
            if not query:
                continue
            api_key = _next_tavily_key() or first_key
            try:
                resp = await client.post(
                    "https://api.tavily.com/search",
                    json={
                        "api_key": api_key,
                        "query": query,
                        "search_depth": "basic",
                        "max_results": 3,
                        "include_answer": False,
                        "include_raw_content": False,
                    },
                )
                if not resp.is_success:
                    continue
                body = resp.json() if resp.content else {}
                for row in body.get("results") or []:
                    if not isinstance(row, dict):
                        continue
                    title = str(row.get("title") or "").strip()
                    url = str(row.get("url") or "").strip()
                    if not title or not url:
                        continue
                    items.append(
                        {
                            "title": title,
                            "url": url,
                            "source": str(row.get("source") or "Tavily").strip(),
                            "published_at": "",
                            "region": "TW" if topic.startswith("T") else ("US" if topic.startswith("U") else "Global"),
                            "impact": "high" if topic in ("G1", "T1", "U1") else "medium",
                            "impact_reason": str(row.get("content") or "").strip()[:260],
                        }
                    )
            except Exception:
                continue

    normalized = _normalize_items(items, max_items=18)
    if not normalized:
        raise RuntimeError("tavily_empty")
    return normalized, session_tag


async def _collect_news_with_grounding() -> list[dict[str, Any]]:
    key = _pick_gemini_key()
    if not key:
        raise RuntimeError("no_gemini_key")

    from google import genai
    from google.genai import types
    from config.models import MODEL_GROUNDING

    prompt = (
        "Use Google Search grounding to collect latest finance news in last 24 hours. "
        "Return JSON only with schema: "
        '{"items":[{"title":"","url":"","source":"","published_at":"","region":"TW|US|Global",'
        '"impact_level":"high|medium|low","impact_reason":""}]}. '
        "Need at least 12 items and include both Taiwan and international markets."
    )

    client = genai.Client(api_key=key)
    response = await asyncio.wait_for(
        asyncio.to_thread(
            client.models.generate_content,
            model=MODEL_GROUNDING,
            contents=prompt,
            config=types.GenerateContentConfig(tools=[types.Tool(google_search=types.GoogleSearch())]),
        ),
        timeout=24,
    )
    payload = _extract_json_object(getattr(response, "text", "") or "")
    items = _normalize_items(payload.get("items"), max_items=18)
    if not items:
        raise RuntimeError("grounding_empty")
    return items


async def _summarize_news_items(items: list[dict[str, Any]], provider: str, session_tag: str) -> dict[str, Any]:
    key = _pick_gemini_key()
    if not key:
        return _normalize_payload(
            {
                "one_minute_brief": _FALLBACK_ONE_MINUTE,
                "brief": _FALLBACK_BRIEF,
                "items": items,
                "table": [],
            },
            provider=provider,
            session_tag=session_tag,
        )

    from google import genai
    from config.models import MODEL_FINAL

    prompt = (
        "你是財經新聞編輯，請把輸入新聞整理成繁體中文，且只輸出 JSON。"
        "JSON schema:\n"
        '{'
        '"one_minute_brief":"",'
        '"brief":[""],'
        '"table":[{"theme":"","impact":"","why":""}],'
        '"items":[{"title":"","url":"","source":"","published_at":"","region":"","impact":"","impact_reason":""}]'
        '}\n'
        "規則：\n"
        "1) one_minute_brief 要 120-180 字，像 1 分鐘新聞口播稿。\n"
        "2) brief 要 3-5 點，聚焦可交易影響。\n"
        "3) table 要 3-5 列，impact 請寫 高/中/低。\n"
        "4) items 最多保留 12 筆，盡量覆蓋台股與美股。\n"
        f"\nInputNewsJson:\n{json.dumps({'items': items}, ensure_ascii=False)}"
    )

    try:
        client = genai.Client(api_key=key)
        resp = await asyncio.wait_for(
            asyncio.to_thread(client.models.generate_content, model=MODEL_FINAL, contents=prompt),
            timeout=28,
        )
        parsed = _extract_json_object(getattr(resp, "text", "") or "")
        if not parsed:
            raise RuntimeError("summary_json_empty")
        if not parsed.get("items"):
            parsed["items"] = items[:12]
        return _normalize_payload(parsed, provider=provider, session_tag=session_tag)
    except Exception as e:
        print(f"[News] summarize failed: {type(e).__name__}: {e}")
        return _normalize_payload(
            {
                "one_minute_brief": _FALLBACK_ONE_MINUTE,
                "brief": _FALLBACK_BRIEF,
                "items": items,
                "table": [],
            },
            provider=provider,
            session_tag=session_tag,
        )


async def _fetch_news_uncached() -> dict[str, Any]:
    try:
        items, session_tag = await _collect_news_with_tavily()
        return await _summarize_news_items(items, provider="tavily", session_tag=session_tag)
    except Exception as e:
        print(f"[News] tavily path failed: {type(e).__name__}: {e}")

    try:
        items = await _collect_news_with_grounding()
        return await _summarize_news_items(items, provider="grounding", session_tag="fallback")
    except Exception as e:
        print(f"[News] grounding path failed: {type(e).__name__}: {e}")

    return await _fetch_news_rss_fallback()


@router.get("/news/brief")
async def get_news_brief():
    """Unified financial news brief, refreshed every 30 minutes server-side."""
    now_ts = datetime.now(timezone.utc).timestamp()
    if _NEWS_CACHE.get("data") and (now_ts - float(_NEWS_CACHE.get("ts") or 0.0) < _NEWS_CACHE_TTL_SEC):
        return _NEWS_CACHE["data"]

    async with _NEWS_LOCK:
        now_ts = datetime.now(timezone.utc).timestamp()
        if _NEWS_CACHE.get("data") and (now_ts - float(_NEWS_CACHE.get("ts") or 0.0) < _NEWS_CACHE_TTL_SEC):
            return _NEWS_CACHE["data"]

        try:
            payload = await _fetch_news_uncached()
        except Exception as e:
            if _NEWS_CACHE.get("data"):
                return _NEWS_CACHE["data"]
            payload = _normalize_payload(
                {
                    "one_minute_brief": f"新聞整理暫時失敗（{type(e).__name__}），目前先顯示預設備援摘要。",
                    "brief": _FALLBACK_BRIEF,
                    "items": [],
                    "table": [],
                },
                provider="error",
                session_tag="error",
            )

        _NEWS_CACHE["data"] = payload
        _NEWS_CACHE["ts"] = now_ts
        return payload
