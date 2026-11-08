"""Local web dashboard: python -m claimit serve"""

import json
from datetime import date
from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from . import ai, db, sources

app = FastAPI(title="ClaimIt")
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")
STATUSES = ["new", "dismissed", "drafted", "filed", "paid"]


def _flash(request: Request) -> str | None:
    return request.query_params.get("msg")


def _back(msg: str, to: str = "/") -> RedirectResponse:
    from urllib.parse import quote
    return RedirectResponse(f"{to}?msg={quote(msg)}", status_code=303)


@app.get("/", response_class=HTMLResponse)
def index(request: Request, show: str = "matches"):
    with db.connect() as conn:
        rows = db.dashboard_rows(conn)
    today = date.today().isoformat()

    def open_(r):
        return not r["deadline"] or r["deadline"] >= today

    active = [r for r in rows if r["status"] not in ("dismissed",) and open_(r)]
    stats = {
        "total": len(rows),
        "unchecked": sum(1 for r in rows if r["match"] is None),
        "likely": sum(1 for r in active if r["match"] == "likely"),
        "possible": sum(1 for r in active if r["match"] == "possible"),
        "potential": sum((r["payout_estimate"] or 0) for r in active
                         if r["match"] == "likely" and r["status"] not in ("paid",)),
        "received": sum((r["amount_received"] or 0) for r in rows),
    }
    if show == "matches":
        rows = [r for r in active if r["match"] in ("likely", "possible") or r["status"] in ("filed", "drafted")]
    elif show == "unchecked":
        rows = [r for r in rows if r["match"] is None]
    try:
        ai.load_profile()
        has_profile = True
    except ai.ProfileMissing:
        has_profile = False
    return templates.TemplateResponse(request, "index.html", {
        "rows": rows, "stats": stats, "show": show, "today": today,
        "msg": _flash(request), "has_profile": has_profile,
    })


@app.post("/fetch")
def fetch():
    seen, new = sources.fetch_feeds()
    return _back(f"Checked {seen} settlements, {new} new.")


@app.post("/match")
def match(limit: int = Form(10)):
    try:
        r = ai.match_pending(limit=limit)
    except (ai.ProfileMissing, ai.NoApiKey) as exc:
        return _back(str(exc))
    msg =f"Checked {r['checked']}: {r['likely']} likely, {r['possible']} possible."
    if r["errors"]:
        msg += f" {len(r['errors'])} failed (see terminal)."
    return _back(msg)


@app.post("/add")
def add(title: str = Form(...), text: str = Form(...), url: str = Form("")):
    sid = sources.add_manual(title, text, url)
    return _back("Added. Run a match check to analyze it.", f"/s/{sid}")


@app.get("/s/{sid}", response_class=HTMLResponse)
def detail(request: Request, sid: str):
    with db.connect() as conn:
        d = db.get_detail(conn, sid)
    if d is None:
        raise HTTPException(404)
    questions = json.loads(d["questions"]) if d["questions"] else []
    return templates.TemplateResponse(request, "detail.html", {
        "d": d, "questions": questions, "statuses": STATUSES, "msg": _flash(request),
    })


@app.post("/s/{sid}/draft")
def draft(sid: str):
    try:
        ai.draft_claim(sid)
    except (ai.ProfileMissing, ai.NoApiKey) as exc:
        return _back(str(exc), f"/s/{sid}")
    return _back("Claim worksheet ready.", f"/s/{sid}")


@app.post("/s/{sid}/status")
def status(sid: str, status: str = Form(...), amount: str = Form("")):
    if status not in STATUSES:
        raise HTTPException(400)
    fields = {"status": status}
    if amount.strip():
        fields["amount_received"] = float(amount)
    with db.connect() as conn:
        db.set_claim(conn, sid, **fields)
    return _back("Saved.", f"/s/{sid}")
