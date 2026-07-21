"""Ni-kshay fetcher — step G. The one genuinely LIVE source.

District TB notifications (public vs private), current year to date.
Response format (verified live 2026-07-15): JSON array of 5 strings:
  [0] JS-style array of district labels
  [1] array of public counts   [2] array of private counts  (aligned)
  [3] HTML district table      [4] summary line with state totals
Known issue: the merged 'Dadra & Nagar Haveli & Daman & Diu' UT is not
accepted under any tested spelling -> those states report 0 districts and are
listed in verify_note rather than silently dropped.
"""
import ast
import hashlib
import json
import logging
import re
import time
from datetime import datetime, timezone

from .. import config
from ..transform.aggregate import slug

log = logging.getLogger("pipeline.nikshay")

MIN_OK_STATES = 30


def _parse_state(payload):
    labels = ast.literal_eval(payload[0]) if payload and payload[0] else []
    pub = ast.literal_eval(payload[1]) if len(payload) > 1 and payload[1] else []
    priv = ast.literal_eval(payload[2]) if len(payload) > 2 and payload[2] else []
    if not (len(labels) == len(pub) == len(priv)):
        raise ValueError("label/count arrays misaligned: {}/{}/{}".format(
            len(labels), len(pub), len(priv)))
    summary = payload[4] if len(payload) > 4 else ""
    totals = re.findall(r"\[\s*(\d+)\s*\]", summary)
    return labels, pub, priv, totals


def fetch(source_id, cfg, session, prev_hash):
    now = datetime.now(timezone.utc)
    from_date = "01/01/{}".format(now.year)
    to_date = now.strftime("%d/%m/%Y")

    # establish session cookie
    session.get(cfg["page_url"], timeout=60)

    out_dir = config.RAW_DIR / cfg["raw_name"] / "ingest_{}".format(
        now.strftime("%Y%m%d_%H%M%S"))
    out_dir.mkdir(parents=True, exist_ok=True)

    docs, failures, total_rows = {}, [], 0
    h = hashlib.sha256()
    for st in config.NIKSHAY_STATES:
        try:
            r = session.post(
                cfg["post_url"],
                data={"FromDate": from_date, "ToDate": to_date, "State": st},
                headers={"X-Requested-With": "XMLHttpRequest",
                         "Referer": cfg["page_url"]},
                timeout=90)
            r.raise_for_status()
            payload = r.json()
            labels, pub, priv, totals = _parse_state(payload)
        except Exception as e:  # noqa: BLE001 — recorded, not swallowed
            failures.append("{}: {}".format(st, str(e)[:80]))
            continue
        if not labels:
            failures.append("{}: 0 districts returned".format(st))
            continue
        with open(out_dir / "tb_{}.json".format(slug(st)), "w") as f:
            json.dump(payload, f)  # verbatim
        h.update(json.dumps([labels, pub, priv], sort_keys=True).encode())
        districts = {}
        for lab, p, pv in zip(labels, pub, priv):
            districts[lab] = {"public": p, "private": pv, "total": p + pv}
        docs[slug(st)] = {
            "state": st, "from_date": from_date, "to_date": to_date,
            "districts": districts,
            "district_count": len(districts),
            "state_public_total": sum(pub), "state_private_total": sum(priv),
            "source_id": "nikshay_tb",
            "updated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        total_rows += len(districts)
        time.sleep(0.3)

    ok_states = len(docs)
    if ok_states < MIN_OK_STATES:
        raise ValueError("VERIFY FAIL nikshay: only {} states returned data "
                         "(need >= {}). Failures: {}".format(
                             ok_states, MIN_OK_STATES, "; ".join(failures)))

    docs["_summary"] = {
        "states_ok": ok_states, "states_failed": failures,
        "district_rows": total_rows, "from_date": from_date,
        "to_date": to_date, "source_id": "nikshay_tb",
        "updated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    content_hash = h.hexdigest()
    unchanged = bool(prev_hash and content_hash == prev_hash)
    note = "{} states OK, {} district rows, {}..{}".format(
        ok_states, total_rows, from_date, to_date)
    if failures:
        note += " | failed: " + "; ".join(failures)
    return {"rows": total_rows, "raw_path": out_dir,
            "content_hash": content_hash, "unchanged": unchanged,
            "agg": {"tb_live": docs}, "verify_note": note}
