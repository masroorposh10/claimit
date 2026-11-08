"""ClaimIt command line.

    python -m claimit fetch            pull new settlements from the feeds
    python -m claimit match [N]        check up to N settlements against your profile (default 10)
    python -m claimit serve            open the dashboard at http://127.0.0.1:8000
"""

import logging
import sys


def main(argv: list[str]) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    cmd = argv[0] if argv else "serve"

    if cmd == "fetch":
        from .sources import fetch_feeds
        seen, new = fetch_feeds()
        print(f"Checked {seen} settlements, {new} new.")
    elif cmd == "match":
        from .ai import NoApiKey, ProfileMissing, match_pending
        try:
            r = match_pending(limit=int(argv[1]) if len(argv) > 1 else 10)
        except (ProfileMissing, NoApiKey) as exc:
            print(exc)
            return 1
        print(f"Checked {r['checked']}: {r['likely']} likely, {r['possible']} possible.")
        for e in r["errors"]:
            print("  failed:", e)
    elif cmd == "serve":
        import uvicorn
        print("ClaimIt running at http://127.0.0.1:8000")
        uvicorn.run("claimit.app:app", host="127.0.0.1", port=8000)
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
