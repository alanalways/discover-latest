"""Reusable news helper functions extracted from routes."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Any


def strip_html_text(value: str) -> str:
    text = re.sub(r"<[^>]+>", " ", value or "")
    return re.sub(r"\s+", " ", text).strip()


def parse_rss_feed(xml_text: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not xml_text:
        return rows

    root = ET.fromstring(xml_text)
    for item in root.findall(".//item"):
        title = strip_html_text(item.findtext("title") or "")
        link = (item.findtext("link") or "").strip()
        source = strip_html_text(item.findtext("source") or "")
        pub = strip_html_text(item.findtext("pubDate") or "")
        desc = strip_html_text(item.findtext("description") or "")
        if not title:
            continue
        rows.append(
            {
                "title": title,
                "url": link,
                "source": source or "RSS",
                "published_at": pub,
                "snippet": desc,
            }
        )
    return rows
