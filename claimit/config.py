from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "claimit.db"
PROFILE_PATH = ROOT / "profile.json"

MODEL = "claude-opus-5-5"

# Public RSS feeds of open settlements. Add more here (any RSS/Atom feed works).
FEEDS = [
    "https://topclassactions.com/category/lawsuit-settlements/open-lawsuit-settlements/feed/",
]

USER_AGENT = "ClaimIt/0.1 (personal settlement tracker)"

# Settlement articles are stripped of HTML before analysis; anything longer
# than this is cut and the cut is logged (articles are normally ~3-8k chars).
MAX_ARTICLE_CHARS = 40_000
