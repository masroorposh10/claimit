"""Claude-powered matching and claim drafting."""

import hashlib
import json
import logging
from concurrent.futures import ThreadPoolExecutor

import anthropic

from . import db
from .config import MODEL, PROFILE_PATH

log = logging.getLogger(__name__)
_client: anthropic.Anthropic | None = None


class NoApiKey(Exception):
    pass


def get_client() -> anthropic.Anthropic:
    """Created lazily so the dashboard still works before a key is set up."""
    global _client
    if _client is None:
        _client = anthropic.Anthropic()
    return _client

HONESTY_RULES = """\
Ground rules (these matter more than finding money):
- Claim forms are signed under penalty of perjury. Filing a claim you do not qualify for is fraud.
- Only call something a "likely" match when the profile gives concrete evidence of eligibility
  (right product/service, right place, right dates).
- Never invent purchases, dates, receipts, or account details. If the profile does not say it,
  it is unknown, and you ask instead of assuming.
- Settlements usually cover one country or region; check that the person lived there."""

MATCH_SCHEMA = {
    "type": "object",
    "properties": {
        "match": {"type": "string", "enum": ["likely", "possible", "unlikely"]},
        "summary": {"type": "string", "description": "One sentence: what the settlement is about."},
        "who_qualifies": {"type": "string", "description": "Class definition in plain words, with dates and regions."},
        "payout": {"type": "string", "description": "What a claimant can get, as stated in the notice."},
        "payout_estimate_usd": {"type": ["number", "null"], "description": "Rough typical payout per person in USD; null if unknown."},
        "deadline": {"type": ["string", "null"], "description": "Claim deadline as YYYY-MM-DD, or null if not stated."},
        "proof_required": {"type": "string", "description": "Whether proof of purchase is needed and what kind."},
        "claim_url": {"type": ["string", "null"], "description": "Official claim/settlement website if stated in the notice."},
        "reasons": {"type": "string", "description": "Why this match level, citing the specific profile entries."},
        "questions_to_confirm": {"type": "array", "items": {"type": "string"},
                                 "description": "Facts the person must confirm before filing."},
    },
    "required": ["match", "summary", "who_qualifies", "payout", "payout_estimate_usd", "deadline",
                 "proof_required", "claim_url", "reasons", "questions_to_confirm"],
    "additionalProperties": False,
}


class ProfileMissing(Exception):
    pass


def load_profile() -> tuple[str, str]:
    """Returns (profile JSON text, short hash so we re-match when it changes)."""
    if not PROFILE_PATH.exists():
        raise ProfileMissing("Create profile.json first (copy profile.example.json).")
    text = PROFILE_PATH.read_text(encoding="utf-8")
    json.loads(text)  # fail early on broken JSON
    return text, hashlib.sha256(text.encode()).hexdigest()[:12]


def _call(system: str, user: str, effort: str, schema: dict | None = None) -> str:
    output_config: dict = {"effort": effort}
    if schema:
        output_config["format"] = {"type": "json_schema", "schema": schema}
    try:
        response = get_client().beta.messages.create(
            model=MODEL,
            max_tokens=16000,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            output_config=output_config,
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": user}],
        )
    except (TypeError, anthropic.AuthenticationError) as exc:
        if isinstance(exc, TypeError) and "authentication" not in str(exc):
            raise
        raise NoApiKey("No working Anthropic API key. Set ANTHROPIC_API_KEY and restart ClaimIt.") from exc
    if response.stop_reason == "refusal":
        raise RuntimeError(f"Model declined: {response.stop_details}")
    if response.stop_reason == "max_tokens":
        raise RuntimeError("Response was cut off (max_tokens).")
    return next(b.text for b in response.content if b.type == "text")


def analyze(settlement, profile_text: str) -> dict:
    system = (
        "You help one person find class-action settlements they genuinely qualify for.\n\n"
        f"{HONESTY_RULES}\n\nTheir profile:\n<profile>\n{profile_text}\n</profile>"
    )
    user = (
        "Read this settlement notice, extract the key facts, and judge whether this person qualifies.\n\n"
        f"<notice title=\"{settlement['title']}\" url=\"{settlement['url'] or ''}\">\n"
        f"{settlement['raw_text']}\n</notice>"
    )
    return json.loads(_call(system, user, effort="low", schema=MATCH_SCHEMA))


def match_pending(limit: int = 10, workers: int = 4) -> dict:
    """Analyze up to `limit` settlements not yet checked against the current profile."""
    profile_text, profile_hash = load_profile()
    with db.connect() as conn:
        todo = db.pending_analysis(conn, profile_hash, limit)

    def work(s):
        try:
            return s["id"], analyze(s, profile_text), None
        except NoApiKey:
            raise  # no point trying the rest
        except Exception as exc:  # keep going; report at the end
            log.exception("Failed on %s", s["title"])
            return s["id"], None, f"{s['title']}: {exc}"

    results = {"checked": 0, "likely": 0, "possible": 0, "errors": []}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for sid, analysis, err in pool.map(work, todo):
            if err:
                results["errors"].append(err)
                continue
            with db.connect() as conn:
                db.save_analysis(conn, sid, profile_hash, analysis)
            results["checked"] += 1
            if analysis["match"] in ("likely", "possible"):
                results[analysis["match"]] += 1
    return results


def draft_claim(settlement_id: str) -> str:
    profile_text, _ = load_profile()
    with db.connect() as conn:
        d = db.get_detail(conn, settlement_id)
    if d is None:
        raise KeyError(settlement_id)
    system = (
        "You prepare a claim worksheet so a person can fill in an official settlement claim form quickly "
        "and truthfully.\n\n"
        f"{HONESTY_RULES}\n\nTheir profile:\n<profile>\n{profile_text}\n</profile>"
    )
    user = f"""Settlement notice:
<notice title="{d['title']}" url="{d['url'] or ''}">
{d['raw_text']}
</notice>

Write a worksheet in Markdown with these sections:
1. **Do you qualify?** A short checklist of each eligibility condition, marked ✅ (profile confirms),
   ❓ (you must confirm), or ❌ (profile contradicts).
2. **Where to file**: the official claim site and deadline, if the notice gives them. If it doesn't,
   say to find the official settlement administrator's site and to beware of look-alike sites.
3. **Form answers**: the answers the form will likely ask for, filled from the profile where it
   supports them. Write [CONFIRM: ...] for anything the profile doesn't state.
4. **Proof to gather**: receipts, account statements, emails, etc.
5. **Before you sign**: one line reminding them the form is signed under penalty of perjury.

If the person clearly does not qualify, say so at the top and keep the rest short."""
    draft = _call(system, user, effort="medium")
    with db.connect() as conn:
        db.set_claim(conn, settlement_id, status="drafted", draft=draft)
    return draft
