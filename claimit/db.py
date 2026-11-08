import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

from .config import DATA_DIR, DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS settlements (
    id          TEXT PRIMARY KEY,
    title       TEXT NOT NULL,
    url         TEXT,
    source      TEXT,
    published   TEXT,
    raw_text    TEXT NOT NULL,
    fetched_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS analyses (
    settlement_id  TEXT PRIMARY KEY REFERENCES settlements(id),
    profile_hash   TEXT NOT NULL,
    match          TEXT NOT NULL,      -- likely | possible | unlikely
    summary        TEXT,
    who_qualifies  TEXT,
    payout         TEXT,
    payout_estimate REAL,              -- rough USD per person, for totals
    deadline       TEXT,               -- YYYY-MM-DD or NULL
    proof_required TEXT,
    claim_url      TEXT,
    reasons        TEXT,
    questions      TEXT,               -- JSON list
    analyzed_at    TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS claims (
    settlement_id   TEXT PRIMARY KEY REFERENCES settlements(id),
    status          TEXT NOT NULL DEFAULT 'new',  -- new | dismissed | drafted | filed | paid
    draft           TEXT,
    amount_received REAL,
    updated_at      TEXT NOT NULL
);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def connect():
    DATA_DIR.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def upsert_settlement(conn, s: dict) -> bool:
    """Insert a settlement; returns True if it was new."""
    cur = conn.execute(
        "INSERT OR IGNORE INTO settlements (id, title, url, source, published, raw_text, fetched_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (s["id"], s["title"], s.get("url"), s.get("source"), s.get("published"), s["raw_text"], now()),
    )
    return cur.rowcount == 1


def save_analysis(conn, settlement_id: str, profile_hash: str, a: dict) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO analyses VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            settlement_id, profile_hash, a["match"], a["summary"], a["who_qualifies"],
            a["payout"], a.get("payout_estimate_usd"), a.get("deadline"), a["proof_required"],
            a.get("claim_url"), a["reasons"], json.dumps(a.get("questions_to_confirm", [])), now(),
        ),
    )


def set_claim(conn, settlement_id: str, **fields) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO claims (settlement_id, updated_at) VALUES (?, ?)", (settlement_id, now())
    )
    for key, value in fields.items():
        if key not in {"status", "draft", "amount_received"}:
            raise ValueError(key)
        conn.execute(f"UPDATE claims SET {key} = ?, updated_at = ? WHERE settlement_id = ?",
                     (value, now(), settlement_id))


def pending_analysis(conn, profile_hash: str, limit: int) -> list[sqlite3.Row]:
    """Settlements never analyzed, or analyzed against an older profile."""
    return conn.execute(
        "SELECT s.* FROM settlements s LEFT JOIN analyses a ON a.settlement_id = s.id "
        "WHERE a.settlement_id IS NULL OR a.profile_hash != ? "
        "ORDER BY s.published DESC LIMIT ?",
        (profile_hash, limit),
    ).fetchall()


def dashboard_rows(conn) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT s.id, s.title, s.url, s.published, a.match, a.summary, a.payout, a.payout_estimate, "
        "a.deadline, a.claim_url, COALESCE(c.status, 'new') AS status, c.amount_received "
        "FROM settlements s LEFT JOIN analyses a ON a.settlement_id = s.id "
        "LEFT JOIN claims c ON c.settlement_id = s.id "
        "ORDER BY CASE a.match WHEN 'likely' THEN 0 WHEN 'possible' THEN 1 WHEN 'unlikely' THEN 3 ELSE 2 END, "
        "a.deadline IS NULL, a.deadline"
    ).fetchall()


def get_detail(conn, settlement_id: str):
    return conn.execute(
        "SELECT s.*, a.match, a.summary, a.who_qualifies, a.payout, a.payout_estimate, a.deadline, "
        "a.proof_required, a.claim_url, a.reasons, a.questions, "
        "COALESCE(c.status, 'new') AS status, c.draft, c.amount_received "
        "FROM settlements s LEFT JOIN analyses a ON a.settlement_id = s.id "
        "LEFT JOIN claims c ON c.settlement_id = s.id WHERE s.id = ?",
        (settlement_id,),
    ).fetchone()
