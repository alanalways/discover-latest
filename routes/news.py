"""Financial news brief API with server-side 30-minute cache."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import html
import re
from typing import Any
import asyncio
import xml.etree.ElementTree as ET

import httpx
from fastapi import APIRouter

router = APIRouter()

_NEWS_CACHE_TTL_SEC = 1800
_NEWS_CACHE: dict[str, Any] = {
    "ts": 0.0,
    "data": None,
}
_NEWS_LOCK = asyncio.Lock()

_RSS_SOURCES = [
    "https://news.google.com/rss/search?q=finance+stock+market+when:1d&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=%E8%B2%A1%E7%B6%93+%E8%82%A1%E5%B8%82+when:1d&hl=zh-TW&gl=TW&ceid=TW:zh-Hant",
]

_IMPACT_KEYWORDS = {
    "rates": ["fed", "fomc", "rate", "rates", "inflation", "cpi", "pce", "yield", "interest"],
    "earnings": ["earnings", "guidance", "forecast", "profit", "revenue", "eps", "財報", "營收"],
    "policy": ["tariff", "sanction", "regulation", "政策", "監管", "法案", "出口", "禁令"],
    "risk": ["war", "geopolitical", "recession", "default", "downgrade", "風險", "衰退", "違約"],
    "ai_semis": ["ai", "nvidia", "chip", "semiconductor", "半導體", "晶片", "伺服器"],
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
                "source": source,
                "published_at": pub,
                "summary": desc[:220],
            }
        )
    return rows


def _build_brief(items: list[dict[str, Any]]) -> list[str]:
    score = {k: 0 for k in _IMPACT_KEYWORDS}
    for row in items:
        text = f"{row.get('title', '')} {row.get('summary', '')}".lower()
        for tag, words in _IMPACT_KEYWORDS.items():
            if any(word in text for word in words):
                score[tag] += 1

    ordered = sorted(score.items(), key=lambda x: x[1], reverse=True)
    bullets: list[str] = []
    label_map = {
        "rates": "利率/通膨",
        "earnings": "財報/財測",
        "policy": "政策/監管",
        "risk": "地緣/總體風險",
        "ai_semis": "AI/半導體",
    }
    for tag, cnt in ordered[:3]:
        if cnt <= 0:
            continue
        bullets.append(f"{label_map.get(tag, tag)}題材升溫（近況 {cnt} 則）")
    if not bullets:
        bullets.append("今日重大財經題材偏分散，建議以風險控管為優先。")
    return bullets


async def _fetch_news_uncached() -> dict[str, Any]:
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

    items = list(dedup.values())[:30]
    brief = _build_brief(items)

    now = datetime.now(timezone.utc)
    return {
        "updated_at": now.isoformat(),
        "next_update_at": (now + timedelta(seconds=_NEWS_CACHE_TTL_SEC)).isoformat(),
        "brief": brief,
        "items": items[:12],
    }


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
            now = datetime.now(timezone.utc)
            payload = {
                "updated_at": now.isoformat(),
                "next_update_at": (now + timedelta(seconds=_NEWS_CACHE_TTL_SEC)).isoformat(),
                "brief": [f"新聞暫時不可用：{e}"],
                "items": [],
            }

        _NEWS_CACHE["data"] = payload
        _NEWS_CACHE["ts"] = now_ts
        return payload
