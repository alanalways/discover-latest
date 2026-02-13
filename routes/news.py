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
from urllib.parse import urlparse
import xml.etree.ElementTree as ET

import httpx
from fastapi import APIRouter

router = APIRouter()

_NEWS_CACHE_TTL_SEC = 1800
_NEWS_CACHE: dict[str, Any] = {"ts": 0.0, "data": None}
_NEWS_LOCK = asyncio.Lock()
_NEWS_CACHE_FILE = os.path.join(os.getcwd(), ".cache", "news_brief_cache.json")
_NEWS_DISK_LOADED = False

_TAVILY_KEYS: list[str] = []
_TAVILY_KEY_INDEX = 0
_TAVILY_LOCK = threading.Lock()
_TAVILY_USAGE_LOCK = threading.Lock()
_TAVILY_DAILY_USAGE: dict[str, int] = {}
_EVENT_CALENDAR_CACHE: list[dict[str, Any]] | None = None

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


def _strip_provider_terms(text: str) -> str:
    cleaned = str(text or "")
    cleaned = re.sub(r"\b(tavily|tavly)\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*[-|]?\s*(tavily|tavly)(?:\.[a-z]+)?\s*$", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _sanitize_payload_inplace(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return payload

    one_minute = _strip_provider_terms(str(payload.get("one_minute_brief") or "").strip())
    if one_minute:
        payload["one_minute_brief"] = one_minute

    brief = payload.get("brief")
    if isinstance(brief, list):
        payload["brief"] = [_strip_provider_terms(str(line)) for line in brief if _strip_provider_terms(str(line))]

    items = payload.get("items")
    if isinstance(items, list):
        clean_items: list[dict[str, Any]] = []
        for row in items:
            if not isinstance(row, dict):
                continue
            title = _strip_provider_terms(str(row.get("title") or "")).splitlines()[0].strip()
            if not title:
                continue
            source = _strip_provider_terms(str(row.get("source") or "")).strip()
            impact_reason = _strip_provider_terms(str(row.get("impact_reason") or "")).strip()
            clean_items.append(
                {
                    **row,
                    "title": title,
                    "source": "" if ("tavily" in source.lower() or "tavly" in source.lower()) else source,
                    "impact_reason": impact_reason,
                    "region": _strip_provider_terms(str(row.get("region") or "")).strip(),
                    "impact": _strip_provider_terms(str(row.get("impact") or "")).strip(),
                }
            )
        payload["items"] = clean_items

    table = payload.get("table")
    if isinstance(table, list):
        payload["table"] = [
            {
                "theme": _strip_provider_terms(str((row or {}).get("theme") or "")).strip(),
                "impact": _strip_provider_terms(str((row or {}).get("impact") or "")).strip(),
                "why": _strip_provider_terms(str((row or {}).get("why") or "")).strip(),
            }
            for row in table
            if isinstance(row, dict)
        ]

    payload["provider"] = ""
    payload["session_tag"] = ""
    return payload


def _load_news_cache_from_disk() -> None:
    global _NEWS_DISK_LOADED
    if _NEWS_DISK_LOADED:
        return
    _NEWS_DISK_LOADED = True
    try:
        if not os.path.exists(_NEWS_CACHE_FILE):
            return
        with open(_NEWS_CACHE_FILE, "r", encoding="utf-8") as f:
            payload = json.load(f)
        if not isinstance(payload, dict):
            return
        ts = float(payload.get("ts") or 0.0)
        data = payload.get("data")
        if ts > 0 and isinstance(data, dict):
            _sanitize_payload_inplace(data)
            _NEWS_CACHE["ts"] = ts
            _NEWS_CACHE["data"] = data
    except Exception:
        return


def _save_news_cache_to_disk(data: dict[str, Any], ts: float) -> None:
    try:
        os.makedirs(os.path.dirname(_NEWS_CACHE_FILE), exist_ok=True)
        with open(_NEWS_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump({"ts": ts, "data": data}, f, ensure_ascii=False)
    except Exception:
        return


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


def _load_event_calendar() -> list[dict[str, Any]]:
    """
    Load event calendar from env JSON.
    Expected schema:
    [
      {"date":"2026-03-18","time_utc":"18:00","type":"FOMC","importance":"high"}
    ]
    """
    global _EVENT_CALENDAR_CACHE
    if _EVENT_CALENDAR_CACHE is not None:
        return _EVENT_CALENDAR_CACHE

    raw = (os.environ.get("NEWS_EVENT_CALENDAR_JSON") or "").strip()
    if not raw:
        _EVENT_CALENDAR_CACHE = []
        return _EVENT_CALENDAR_CACHE
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            rows: list[dict[str, Any]] = []
            for item in parsed:
                if not isinstance(item, dict):
                    continue
                date_text = str(item.get("date") or "").strip()
                time_text = str(item.get("time_utc") or "00:00").strip()
                if len(date_text) != 10:
                    continue
                rows.append(
                    {
                        "date": date_text,
                        "time_utc": time_text if len(time_text) >= 4 else "00:00",
                        "type": str(item.get("type") or "").strip(),
                        "importance": str(item.get("importance") or "").strip().lower() or "medium",
                    }
                )
            _EVENT_CALENDAR_CACHE = rows
            return rows
    except Exception:
        pass
    _EVENT_CALENDAR_CACHE = []
    return _EVENT_CALENDAR_CACHE


def _is_special_window(now_tw: datetime) -> bool:
    """
    Special window:
    - calendar event day and now within [-6h, +6h] around event UTC time
    - or manually forced by env NEWS_FORCE_SPECIAL=1
    """
    force = str(os.environ.get("NEWS_FORCE_SPECIAL", "")).strip().lower() in {"1", "true", "yes", "on"}
    if force:
        return True

    now_utc = now_tw.astimezone(timezone.utc)
    events = _load_event_calendar()
    if not events:
        return False

    for ev in events:
        date_text = str(ev.get("date") or "").strip()
        time_text = str(ev.get("time_utc") or "00:00").strip()
        try:
            hour = int(time_text.split(":")[0])
            minute = int(time_text.split(":")[1]) if ":" in time_text else 0
            event_dt = datetime.strptime(date_text, "%Y-%m-%d").replace(
                tzinfo=timezone.utc, hour=hour, minute=minute, second=0, microsecond=0
            )
            delta_h = abs((now_utc - event_dt).total_seconds()) / 3600.0
            if delta_h <= 6.0:
                return True
        except Exception:
            continue
    return False


def _build_query_plan(now_tw: datetime) -> tuple[str, list[dict[str, Any]]]:
    """
    Returns a plan list:
      [{"topic":"G1","depth":"basic|advanced","max_results":3,"cost":1|2}, ...]
    """
    session_tag, topics = _scheduled_topic_keys(now_tw)
    special = _is_special_window(now_tw)

    plan: list[dict[str, Any]] = []
    for t in topics:
        plan.append({"topic": t, "depth": "basic", "max_results": 3, "cost": 1})

    if special:
        # Promote macro/geopolitics depth and add missing key themes.
        boosted_topics = {"G1", "G2"}
        existing = {str(p.get("topic")) for p in plan}
        for p in plan:
            if p.get("topic") in boosted_topics:
                p["depth"] = "advanced"
                p["cost"] = 2
                p["max_results"] = 4
        for t in ("G1", "G2"):
            if t not in existing:
                plan.append({"topic": t, "depth": "advanced", "max_results": 4, "cost": 2})

    return (f"{session_tag}{':special' if special else ''}", plan)


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


def _get_tavily_daily_budget() -> int:
    raw = (os.environ.get("TAVILY_DAILY_BUDGET") or "").strip()
    if raw.isdigit():
        return max(1, int(raw))
    # Default from monthly budget profile (e.g. 5000/month -> ~238/day on 21 trading days).
    monthly_raw = (os.environ.get("TAVILY_MONTHLY_BUDGET") or "").strip()
    trading_days_raw = (os.environ.get("TAVILY_TRADING_DAYS_PER_MONTH") or "").strip()
    monthly = int(monthly_raw) if monthly_raw.isdigit() else 5000
    trading_days = int(trading_days_raw) if trading_days_raw.isdigit() else 21
    return max(1, int(monthly / max(1, trading_days)))


def _reserve_tavily_credit(cost: int) -> bool:
    if cost <= 0:
        return True
    today = _taipei_now().strftime("%Y-%m-%d")
    budget = _get_tavily_daily_budget()
    with _TAVILY_USAGE_LOCK:
        used = _TAVILY_DAILY_USAGE.get(today, 0)
        remain = max(0, budget - used)
        if remain < cost:
            return False
        _TAVILY_DAILY_USAGE[today] = used + cost
        # Keep memory small: keep only today/yesterday counters.
        if len(_TAVILY_DAILY_USAGE) > 3:
            keys = sorted(_TAVILY_DAILY_USAGE.keys())
            for k in keys[:-2]:
                _TAVILY_DAILY_USAGE.pop(k, None)
        return True


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
        # Some upstream rows include provider names in next line; keep only headline line.
        title = title.splitlines()[0].strip() if title else ""
        # Hard-strip provider traces from anywhere in title.
        title = _strip_provider_terms(title)
        url = str(item.get("url") or item.get("link") or "").strip()
        source = _strip_provider_terms(str(item.get("source") or "").strip())
        impact_reason = _strip_provider_terms(str(item.get("impact_reason") or "").strip())
        if not title or not url:
            continue
        source_lc = source.lower()
        if source_lc in {"tavily", "tavly", "tavily ai", "news", "unknown"} or "tavily" in source_lc or "tavly" in source_lc:
            try:
                host = urlparse(url).netloc.lower()
                host = host.replace("www.", "")
                source = host.split(":")[0] if host else ""
            except Exception:
                source = ""
        # Do not leak upstream provider labels to UI.
        if "tavily" in source.lower() or "tavly" in source.lower():
            source = ""
        # Remove provider traces from reason as well.
        impact_reason = re.sub(r"\b(tavily|tavly)\b", "", impact_reason, flags=re.IGNORECASE)
        impact_reason = re.sub(r"\s+", " ", impact_reason).strip()
        key = f"{title.lower()}|{url.lower()}"
        if key in seen:
            continue
        seen.add(key)
        rows.append(
            {
                "title": title,
                "url": url,
                "source": source,
                "published_at": str(item.get("published_at") or item.get("published") or "").strip(),
                "region": _strip_provider_terms(str(item.get("region") or "")).strip(),
                "impact": _strip_provider_terms(str(item.get("impact") or item.get("impact_level") or "")).strip(),
                "impact_reason": impact_reason,
            }
        )
        if len(rows) >= max_items:
            break
    return rows


def _build_rule_based_summary(items: list[dict[str, Any]]) -> dict[str, Any]:
    """Build a deterministic fallback summary from fetched headlines."""
    if not items:
        return {
            "one_minute_brief": _FALLBACK_ONE_MINUTE,
            "brief": _FALLBACK_BRIEF,
            "table": [],
            "items": [],
        }

    keyword_theme_map: dict[str, tuple[str, str, str]] = {
        "fomc": ("利率政策", "高", "聯準會政策預期直接影響股債估值與風險偏好。"),
        "fed": ("利率政策", "高", "聯準會政策預期直接影響股債估值與風險偏好。"),
        "rate": ("利率政策", "高", "利率變動會改變資金成本與估值中樞。"),
        "yield": ("利率政策", "高", "公債殖利率上行通常壓抑高估值成長股。"),
        "cpi": ("通膨數據", "高", "通膨數據會影響後續利率路徑與市場定價。"),
        "inflation": ("通膨數據", "高", "通膨數據會影響後續利率路徑與市場定價。"),
        "earnings": ("企業財報", "中", "財報與財測牽動板塊輪動與個股評價。"),
        "guidance": ("企業財報", "中", "財測修正會放大短線波動。"),
        "ai": ("AI 供應鏈", "中", "AI 訂單與資本支出變化會影響半導體與伺服器鏈。"),
        "nvidia": ("AI 供應鏈", "中", "AI 龍頭訊號常帶動整體科技情緒。"),
        "semiconductor": ("AI 供應鏈", "中", "半導體景氣與庫存週期影響台美科技權值。"),
        "chip": ("AI 供應鏈", "中", "晶片供需變化會反映到權值股獲利預期。"),
        "oil": ("能源與原物料", "中", "油價變動會影響通膨與運輸、製造成本。"),
        "crude": ("能源與原物料", "中", "油價變動會影響通膨與運輸、製造成本。"),
        "war": ("地緣政治", "高", "衝突或制裁會改變供應鏈與避險需求。"),
        "sanction": ("地緣政治", "高", "制裁升級可能造成供應鏈中斷與風險溢價上升。"),
        "conflict": ("地緣政治", "高", "地緣風險上升通常壓抑風險資產。"),
        "usd": ("匯率與美元", "中", "美元走勢會影響外資流向與新興市場評價。"),
        "dollar": ("匯率與美元", "中", "美元走勢會影響外資流向與新興市場評價。"),
        "fx": ("匯率與美元", "中", "匯率波動會改變跨國企業獲利換算。"),
        "futures": ("期貨與波動", "中", "期貨盤勢可提前反映現貨開盤方向。"),
        "vix": ("期貨與波動", "中", "波動率上升代表避險需求增加。"),
        "volatility": ("期貨與波動", "中", "波動擴大時，追價風險提高。"),
    }
    negative_words = ("drop", "lower", "fear", "selloff", "down", "fall", "slump", "risk-off")
    positive_words = ("rise", "higher", "gain", "rally", "up", "beat", "surge", "risk-on")

    theme_count: dict[str, int] = {}
    theme_meta: dict[str, tuple[str, str]] = {}
    pos = 0
    neg = 0

    for row in items[:12]:
        text = f"{row.get('title', '')} {row.get('impact_reason', '')}".lower()
        matched = False
        for kw, (theme, impact, why) in keyword_theme_map.items():
            if kw in text:
                matched = True
                theme_count[theme] = theme_count.get(theme, 0) + 1
                theme_meta[theme] = (impact, why)
        if not matched:
            theme_count["市場情緒"] = theme_count.get("市場情緒", 0) + 1
            theme_meta["市場情緒"] = ("中", "整體新聞流向反映短線風險偏好變化。")

        if any(w in text for w in positive_words):
            pos += 1
        if any(w in text for w in negative_words):
            neg += 1

    ranked = sorted(theme_count.items(), key=lambda x: x[1], reverse=True)
    top_themes = [name for name, _ in ranked[:3]]
    if not top_themes:
        top_themes = ["市場情緒", "企業財報", "利率政策"]

    if neg > pos:
        risk_tone = "偏防禦"
        action_hint = "建議控制槓桿與部位集中度，等待波動收斂再擴張風險。"
    elif pos > neg:
        risk_tone = "偏風險承擔"
        action_hint = "可聚焦強勢主軸分批布局，但仍需設定停損與部位上限。"
    else:
        risk_tone = "區間震盪"
        action_hint = "建議以分批進出與紀律風控為主，避免追高殺低。"

    tw_focus = 0
    us_focus = 0
    global_focus = 0
    for row in items[:12]:
        region = str(row.get("region") or "").strip().lower()
        title_lc = str(row.get("title") or "").lower()
        if region in {"tw", "taiwan"} or any(tok in title_lc for tok in ("台股", "台積電", "聯發科", "鴻海")):
            tw_focus += 1
        elif region in {"us", "usa", "united states"} or any(tok in title_lc for tok in ("nasdaq", "s&p", "dow", "nvidia", "apple", "tesla")):
            us_focus += 1
        else:
            global_focus += 1

    market_link = "台股與美股均受同一組總體與科技主線牽動。"
    if tw_focus > us_focus and tw_focus >= 2:
        market_link = "台股權值與半導體主線較強，美股偏向跟隨利率與科技龍頭訊號。"
    elif us_focus > tw_focus and us_focus >= 2:
        market_link = "美股科技與利率敏感族群主導，台股多受美股風險偏好外溢影響。"

    headline_focus = []
    for row in items[:4]:
        t = str(row.get("title") or "").strip()
        if t:
            headline_focus.append(t[:36])

    # Force a market-linked one-minute brief so users can quickly connect news -> market impact.
    one_minute = (
        f"一分鐘看市場（最新 {min(len(items), 12)} 則）：主軸集中在「{'、'.join(top_themes)}」，"
        f"短線風格偏向{risk_tone}。"
        f"{market_link}"
        f"台股可先看權值與半導體，"
        f"美股可先看大型科技與利率敏感族群。"
        f"{action_hint}"
        f"{(' 焦點事件：' + ' / '.join(headline_focus[:2]) + '。') if headline_focus else ''}"
    )

    brief_lines: list[str] = []
    for theme in top_themes[:3]:
        impact, why = theme_meta.get(theme, ("中", "留意該主題對資金輪動的連鎖效應。"))
        brief_lines.append(f"{theme}（影響{impact}）：{why}")
    for row in items[:3]:
        title = str(row.get("title") or "").strip()
        region = str(row.get("region") or "").strip() or "Global"
        reason = _strip_provider_terms(str(row.get("impact_reason") or "")).strip()
        if title:
            if reason:
                brief_lines.append(f"新聞連結市場（{region}）：{title[:50]} -> {reason[:42]}。")
            else:
                brief_lines.append(f"新聞連結市場（{region}）：{title[:60]}。")

    if len(brief_lines) < 3:
        brief_lines.extend(_FALLBACK_BRIEF[: 3 - len(brief_lines)])

    table = []
    for theme in top_themes[:4]:
        impact, why = theme_meta.get(theme, ("中", "觀察後續消息是否擴散到主要權值股。"))
        table.append({"theme": theme, "impact": impact, "why": why})

    return {
        "one_minute_brief": one_minute,
        "brief": brief_lines[:5],
        "table": table[:8],
        "items": items[:12],
    }


def _normalize_payload(payload: dict[str, Any], provider: str = "unknown", session_tag: str = "") -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    brief = payload.get("brief") if isinstance(payload, dict) else None
    items = payload.get("items") if isinstance(payload, dict) else None
    table = payload.get("table") if isinstance(payload, dict) else None
    one_minute = str(payload.get("one_minute_brief") or "").strip()

    norm_brief = [_strip_provider_terms(str(x).strip()) for x in (brief or []) if _strip_provider_terms(str(x).strip())]
    if not norm_brief:
        norm_brief = list(_FALLBACK_BRIEF)

    norm_items = _normalize_items(items, max_items=12)
    # UI policy: do not display upstream provider labels in the dashboard card.
    for row in norm_items:
        if isinstance(row, dict):
            row["source"] = ""
    norm_table = table if isinstance(table, list) else []
    one_minute = _strip_provider_terms(one_minute)
    if not one_minute:
        one_minute = "；".join(norm_brief[:2]) or _FALLBACK_ONE_MINUTE
    if ("台股" not in one_minute and "美股" not in one_minute) and norm_brief:
        one_minute = f"{one_minute} 台股可留意權值與半導體，美股可觀察科技龍頭與利率敏感族群。"

    payload_out = {
        "updated_at": now.isoformat(),
        "next_update_at": (now + timedelta(seconds=_NEWS_CACHE_TTL_SEC)).isoformat(),
        "one_minute_brief": one_minute,
        "brief": norm_brief[:5],
        "items": norm_items,
        "table": norm_table[:8],
        # Hide upstream/session internals from UI to avoid provider leakage.
        "provider": "",
        "session_tag": "",
    }
    return _sanitize_payload_inplace(payload_out)


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
    session_tag, query_plan = _build_query_plan(now_tw)
    if not query_plan:
        raise RuntimeError("tavily_no_plan")
    items: list[dict[str, Any]] = []

    async with httpx.AsyncClient(timeout=16.0) as client:
        for q in query_plan:
            topic = str(q.get("topic") or "")
            query = _TOPIC_QUERY_MAP.get(topic)
            if not query:
                continue
            cost = int(q.get("cost") or 1)
            if not _reserve_tavily_credit(cost):
                continue
            api_key = _next_tavily_key() or first_key
            try:
                resp = await client.post(
                    "https://api.tavily.com/search",
                    json={
                        "api_key": api_key,
                        "query": query,
                        "search_depth": str(q.get("depth") or "basic"),
                        "max_results": int(q.get("max_results") or 3),
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
                            "source": str(row.get("source") or "News").strip(),
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
    # Default to deterministic summary from collected headlines to avoid model timeout
    # and keep output tightly linked to latest Tavily/Grounding items.
    rule_payload = _build_rule_based_summary(items)
    key = _pick_gemini_key()
    use_gemini_summary = str(os.environ.get("NEWS_USE_GEMINI_SUMMARY", "0")).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    if not key or not use_gemini_summary:
        return _normalize_payload(rule_payload, provider=provider, session_tag=session_tag)

    from google import genai
    from config.models import MODEL_FINAL

    compact_items = items[:10]
    digest_lines = []
    for row in compact_items:
        title = str(row.get("title") or "").strip()
        region = str(row.get("region") or "").strip() or "Global"
        reason = str(row.get("impact_reason") or "").strip()
        if title:
            digest_lines.append(f"- [{region}] {title} | {reason[:100]}")
    digest_text = "\n".join(digest_lines[:10])

    prompt = (
        "你是財經新聞總編，請把輸入新聞整理成繁體中文，且只輸出 JSON。"
        "JSON schema:\n"
        '{'
        '"one_minute_brief":"",'
        '"brief":[""],'
        '"table":[{"theme":"","impact":"","why":""}],'
        '"items":[{"title":"","url":"","source":"","published_at":"","region":"","impact":"","impact_reason":""}]'
        '}\n'
        "規則：\n"
        "1) one_minute_brief 120-180 字，需明確說明『新聞重點如何連結台股/美股』。\n"
        "2) brief 產出 3-5 點，每點格式為：事件 -> 影響市場/族群 -> 可能交易意義。\n"
        "3) table 產出 3-5 列，impact 只能是 高/中/低，why 要可執行。\n"
        "4) items 最多 10 筆，保留原標題與連結，不要改寫來源名稱。\n"
        "5) 不要輸出 markdown，不要提到資料供應商名稱。\n"
        f"\nInputDigest:\n{digest_text}\n"
        f"\nInputNewsJson:\n{json.dumps({'items': compact_items}, ensure_ascii=False)}"
    )

    try:
        client = genai.Client(api_key=key)
        resp = await asyncio.wait_for(
            asyncio.to_thread(client.models.generate_content, model=MODEL_FINAL, contents=prompt),
            timeout=9,
        )
        parsed = _extract_json_object(getattr(resp, "text", "") or "")
        if not parsed:
            raise RuntimeError("summary_json_empty")
        if not parsed.get("items"):
            parsed["items"] = items[:12]
        return _normalize_payload(parsed, provider=provider, session_tag=session_tag)
    except Exception as e:
        print(f"[News] summarize fallback: {type(e).__name__}")
        return _normalize_payload(rule_payload, provider=provider, session_tag=session_tag)


async def _fetch_news_uncached() -> dict[str, Any]:
    try:
        items, session_tag = await _collect_news_with_tavily()
        return await _summarize_news_items(items, provider="system", session_tag=session_tag)
    except Exception as e:
        print(f"[News] tavily path failed: {type(e).__name__}: {e}")

    try:
        items = await _collect_news_with_grounding()
        return await _summarize_news_items(items, provider="system", session_tag="fallback")
    except Exception as e:
        print(f"[News] grounding path failed: {type(e).__name__}: {e}")

    return await _fetch_news_rss_fallback()


@router.get("/news/brief")
async def get_news_brief():
    """Unified financial news brief, refreshed every 30 minutes server-side."""
    _load_news_cache_from_disk()
    now_ts = datetime.now(timezone.utc).timestamp()
    if _NEWS_CACHE.get("data") and (now_ts - float(_NEWS_CACHE.get("ts") or 0.0) < _NEWS_CACHE_TTL_SEC):
        if isinstance(_NEWS_CACHE.get("data"), dict):
            _sanitize_payload_inplace(_NEWS_CACHE["data"])
        return _NEWS_CACHE["data"]

    async with _NEWS_LOCK:
        now_ts = datetime.now(timezone.utc).timestamp()
        if _NEWS_CACHE.get("data") and (now_ts - float(_NEWS_CACHE.get("ts") or 0.0) < _NEWS_CACHE_TTL_SEC):
            if isinstance(_NEWS_CACHE.get("data"), dict):
                _sanitize_payload_inplace(_NEWS_CACHE["data"])
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
        _save_news_cache_to_disk(payload, now_ts)
        return payload
