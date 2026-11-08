"""Pull open settlements from public RSS feeds (or a pasted notice)."""

import hashlib
import html
import logging
import re

import feedparser

from . import db
from .config import FEEDS, MAX_ARTICLE_CHARS, USER_AGENT

log = logging.getLogger(__name__)

_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\n\s*\n+")


def html_to_text(raw: str) -> str:
    raw = re.sub(r"(?is)<(script|style).*?</\1>", "", raw)
    raw = re.sub(r"(?i)<br\s*/?>|</p>|</li>|</h\d>", "\n", raw)
    text = html.unescape(_TAG.sub("", raw))
    text = _WS.sub("\n\n", text).strip()
    if len(text) > MAX_ARTICLE_CHARS:
        log.warning("Article cut from %d to %d chars", len(text), MAX_ARTICLE_CHARS)
        text = text[:MAX_ARTICLE_CHARS]
    return text


def fetch_feeds() -> tuple[int, int]:
    """Returns (items seen, new items saved)."""
    seen = new = 0
    with db.connect() as conn:
        for url in FEEDS:
            feed = feedparser.parse(url, agent=USER_AGENT)
            if feed.bozo and not feed.entries:
                log.error("Could not read feed %s: %s", url, feed.bozo_exception)
                continue
            for e in feed.entries:
                seen += 1
                body = e.get("content", [{}])[0].get("value") or e.get("summary", "")
                new += db.upsert_settlement(conn, {
                    "id": _short_id(e.get("id") or e.link),
                    "title": html.unescape(e.title),
                    "url": e.get("link"),
                    "source": feed.feed.get("title", url),
                    "published": _iso(e),
                    "raw_text": html_to_text(body),
                })
    return seen, new


def add_manual(title: str, text: str, url: str | None = None) -> str:
    """Add a settlement notice you found yourself (e.g. a Canadian one)."""
    sid = "m" + _short_id(title + text)
    with db.connect() as conn:
        db.upsert_settlement(conn, {
            "id": sid, "title": title.strip(), "url": url or None,
            "source": "Added manually", "published": db.now(),
            "raw_text": html_to_text(text),
        })
    return sid


def _short_id(key: str) -> str:
    """URL-safe stable id (feed GUIDs are often full URLs)."""
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def _iso(entry) -> str | None:
    t = entry.get("published_parsed")
    if not t:
        return None
    return f"{t.tm_year:04d}-{t.tm_mon:02d}-{t.tm_mday:02d}"
