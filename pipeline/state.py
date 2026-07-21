"""Resumable pipeline state.

Single source of truth = data/state/pipeline_state.json.
After every source attempt the STATE table in docs/PIPELINE_CHECKLIST.md is
regenerated (between the STATE:BEGIN/STATE:END markers) so a fresh session —
human or Claude — can resume from the file alone.
"""
import json
import re
from datetime import datetime, timezone, timedelta

from . import config


def _now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load():
    if config.STATE_FILE.exists():
        with open(config.STATE_FILE) as f:
            return json.load(f)
    return {"sources": {}, "firestore": {"date": None, "writes_today": 0}}


def save(state):
    config.ensure_dirs()
    tmp = config.STATE_FILE.with_suffix(".json.tmp")
    with open(tmp, "w") as f:
        json.dump(state, f, indent=2, sort_keys=True)
    tmp.replace(config.STATE_FILE)
    sync_checklist(state)


def src(state, source_id):
    return state["sources"].setdefault(source_id, {
        "status": "todo", "last_attempt": None, "last_success": None,
        "rows": None, "raw_path": None, "content_hash": None,
        "error": None, "verify_note": None, "published_docs": None,
        "last_published": None, "runs": 0,
    })


def record_attempt(state, source_id):
    s = src(state, source_id)
    s["last_attempt"] = _now_iso()
    s["runs"] = s.get("runs", 0) + 1
    save(state)


def record_success(state, source_id, rows, raw_path, content_hash,
                   verify_note, unchanged=False):
    s = src(state, source_id)
    s.update(status=("unchanged" if unchanged else "ok"),
             last_success=_now_iso(), rows=rows, raw_path=str(raw_path),
             content_hash=content_hash, error=None, verify_note=verify_note)
    save(state)


def record_error(state, source_id, error, verify_note=None):
    s = src(state, source_id)
    s.update(status="error", error=str(error)[:500])
    if verify_note:
        s["verify_note"] = verify_note
    save(state)


def record_published(state, source_id, n_docs):
    s = src(state, source_id)
    s.update(published_docs=n_docs, last_published=_now_iso())
    save(state)


def record_skipped(state, source_id, why):
    s = src(state, source_id)
    s.update(status="skipped", error=None, verify_note=why)
    save(state)


def _parse(ts):
    return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(
        tzinfo=timezone.utc)


def is_due(state, source_id, cadence_h, force=False):
    if force:
        return True
    s = src(state, source_id)
    if s["status"] == "error":
        # back off instead of retrying every daemon tick (a down site would
        # otherwise get hit every 60s): 30min for hourly sources, up to 6h
        # for daily/weekly ones.
        if not s["last_attempt"]:
            return True
        retry_h = min(6.0, max(0.5, cadence_h / 4.0))
        return (datetime.now(timezone.utc) - _parse(s["last_attempt"])
                >= timedelta(hours=retry_h))
    if s["status"] == "skipped":  # e.g. shrug awaiting manual URLs — don't
        if not s["last_attempt"]:  # re-announce it every 60s tick
            return True
        return (datetime.now(timezone.utc) - _parse(s["last_attempt"])
                >= timedelta(hours=cadence_h))
    if s["status"] == "todo" or not s["last_success"]:
        return True
    return (datetime.now(timezone.utc) - _parse(s["last_success"])
            >= timedelta(hours=cadence_h))


# ---- Firestore daily write budget -----------------------------------------

def writes_available(state):
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    fs = state["firestore"]
    if fs.get("date") != today:
        fs["date"] = today
        fs["writes_today"] = 0
    return config.FIRESTORE_DAILY_WRITE_CAP - fs["writes_today"]


def add_writes(state, n):
    writes_available(state)  # roll the date if needed
    state["firestore"]["writes_today"] += n
    save(state)


# ---- Checklist sync --------------------------------------------------------

_BEGIN, _END = "<!-- STATE:BEGIN (auto-generated, do not hand-edit) -->", "<!-- STATE:END -->"

_ICON = {"ok": "✅ ok", "unchanged": "✅ unchanged", "error": "❌ error",
         "todo": "☐ todo", "skipped": "⏭ skipped"}


def render_state_table(state):
    lines = [
        "| Step | Source | Status | Rows | Last success | Published docs | Raw path | Notes / error |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for sid, cfg in config.SOURCES.items():
        s = state["sources"].get(sid, {})
        status = _ICON.get(s.get("status", "todo"), s.get("status", "todo"))
        note = s.get("error") or s.get("verify_note") or cfg.get("note", "")
        note = (note or "").replace("|", "/").replace("\n", " ")[:160]
        lines.append("| {step} | `{sid}` | {status} | {rows} | {succ} | {pub} | {raw} | {note} |".format(
            step=cfg["step"], sid=sid, status=status,
            rows=s.get("rows") if s.get("rows") is not None else "—",
            succ=(s.get("last_success") or "—"),
            pub=s.get("published_docs") if s.get("published_docs") is not None else "—",
            raw=(s.get("raw_path") or "—"),
            note=note))
    fs = state.get("firestore", {})
    lines.append("")
    lines.append("_Firestore writes today ({d}): {w} / {cap} cap._".format(
        d=fs.get("date"), w=fs.get("writes_today", 0),
        cap=config.FIRESTORE_DAILY_WRITE_CAP))
    lines.append("_Table auto-updated {t}._".format(t=_now_iso()))
    return "\n".join(lines)


def sync_checklist(state):
    p = config.CHECKLIST_FILE
    if not p.exists():
        return
    text = p.read_text()
    if _BEGIN not in text or _END not in text:
        return
    block = _BEGIN + "\n\n" + render_state_table(state) + "\n\n" + _END
    new = re.sub(re.escape(_BEGIN) + r".*?" + re.escape(_END), block,
                 text, flags=re.S)
    p.write_text(new)
