"""PMJAY empanelled-hospitals fetcher — step H.

Flow (verified live 2026-07-15):
  1. GET  Search/            -> jsessionid cookie
  2. POST empanelApplicationForm.htm?actionVal=GETLOCATIONS&locType=ST&locVal=0
        -> "[35~ANDAMAN AND NICOBAR ISLANDS, 28~ANDHRA PRADESH, ...]"
  3. per state: locType=DT&locVal=<code> -> district code~name list
  4. per district: POST empnlWorkFlow.htm (form) -> HTML table, rows carry
     <td data-title="Hospital Type">Public|Private</td> (value may be wrapped
     in nested tags — strip before classifying). Fixed 10 rows/page; page 1
     embeds 'Total no of records: N'. Pages 2+ replicate fn_pagination(): the
     same form with applSearch/draftMenu EMPTIED plus actionFlag & pageNo in
     the URL query.
Aggregate = public/private hospital counts per district, one doc per state.
Set env PMJAY_STATE_LIMIT=<n> to test on a subset.
"""
import hashlib
import json
import logging
import math
import os
import re
import time
from datetime import datetime, timezone

from .. import config
from ..transform.aggregate import slug

log = logging.getLogger("pipeline.pmjay")

MAX_PAGES_PER_DISTRICT = 400  # safety valve (4000 hospitals/district)
MIN_OK_STATES = 30
SKIP_LOCATION_CODES = {"997"}  # "Outside State" pseudo-district

_TYPE_RE = re.compile(
    r'<td[^>]*data-title="Hospital Type"[^>]*>(.*?)</td>', re.S)
_TOTAL_RE = re.compile(r"Total no of records:\s*(\d+)")
_TAGS_RE = re.compile(r"<[^>]+>")


def _parse_locations(text):
    """'[466~AHMED NAGAR, 467~AKOLA, ...]' -> [(code, name), …]"""
    return re.findall(r"(\d+)~([^,\]]+)", text)


def _search_page(session, cfg, state_code, district_code, page_no):
    data = {
        "actionFlag": "ViewRegisteredHosptlsNew", "search": "Y",
        "appReadOnly": "Y",
        "searchState": state_code, "searchDistrict": district_code,
        "searchHospType": "-1", "searchSpeciality": "-1",
        "searchHospName": "-1", "empanelmentType": "-1",
    }
    url = cfg["search_url"]
    if page_no == 1:
        data.update(applSearch="N", draftMenu="N")
    else:  # fn_pagination() semantics, verified live
        data.update(applSearch="", draftMenu="", pageNo=str(page_no))
        url = "{}?actionFlag=ViewRegisteredHosptlsNew&pageNo={}".format(
            url, page_no)
    r = session.post(url, data=data,
                     headers={"Referer": cfg["session_url"]}, timeout=120)
    r.raise_for_status()
    return r.text


def _count_types(html):
    # values seen live: 'Public', 'Private', 'Private (For Profit)',
    # 'Private (Not For Profit)' — classify by prefix
    types = [_TAGS_RE.sub("", t).strip().lower() for t in _TYPE_RE.findall(html)]
    pub = sum(1 for t in types if t.startswith("public"))
    priv = sum(1 for t in types if t.startswith("private"))
    other = len(types) - pub - priv
    return pub, priv, other, len(types)


def _total_records(html):
    m = _TOTAL_RE.search(html)
    return int(m.group(1)) if m else None


def fetch(source_id, cfg, session, prev_hash):
    now = datetime.now(timezone.utc)
    session.get(cfg["session_url"], timeout=60)  # jsessionid

    r = session.post(
        cfg["locations_url"],
        params={"actionVal": "GETLOCATIONS", "locType": "ST", "locVal": "0"},
        headers={"X-Requested-With": "XMLHttpRequest"}, timeout=60)
    r.raise_for_status()
    states = _parse_locations(r.text)
    if len(states) < 30:
        raise ValueError("VERIFY FAIL pmjay: state list returned only {} "
                         "entries: {!r}".format(len(states), r.text[:200]))

    limit = os.environ.get("PMJAY_STATE_LIMIT")
    if limit:
        states = states[: int(limit)]
        log.warning("PMJAY_STATE_LIMIT=%s — subset run (not a full ingest)",
                    limit)

    out_dir = config.RAW_DIR / cfg["raw_name"] / "ingest_{}".format(
        now.strftime("%Y%m%d_%H%M%S"))
    (out_dir / "html").mkdir(parents=True, exist_ok=True)

    docs, failures, n_districts = {}, [], 0
    h = hashlib.sha256()
    for st_code, st_name in states:
        st_name = st_name.strip()
        try:
            rd = session.post(
                cfg["locations_url"],
                params={"actionVal": "GETLOCATIONS", "locType": "DT",
                        "locVal": st_code},
                headers={"X-Requested-With": "XMLHttpRequest"}, timeout=60)
            rd.raise_for_status()
            districts = [(c, n.strip()) for c, n in _parse_locations(rd.text)
                         if c not in SKIP_LOCATION_CODES]
        except Exception as e:  # noqa: BLE001
            failures.append("{} districts-list: {}".format(st_name, str(e)[:80]))
            continue

        st_doc = {}
        for dt_code, dt_name in districts:
            pub = priv = other = 0
            try:
                html = _search_page(session, cfg, st_code, dt_code, 1)
                expected = _total_records(html)
                p, pv, o, page_rows = _count_types(html)
                pub, priv, other = p, pv, o
                fn = "html/{}_{}_p1.html".format(slug(st_name), slug(dt_name))
                with open(out_dir / fn, "w") as f:
                    f.write(html)  # verbatim first page as evidence
                if expected and page_rows:
                    n_pages = min(math.ceil(expected / page_rows),
                                  MAX_PAGES_PER_DISTRICT)
                    for page_no in range(2, n_pages + 1):
                        html = _search_page(session, cfg, st_code, dt_code,
                                            page_no)
                        p, pv, o, rows_n = _count_types(html)
                        if rows_n == 0:
                            failures.append("{}/{}: page {} empty (expected "
                                            "{} records)".format(
                                                st_name, dt_name, page_no,
                                                expected))
                            break
                        pub, priv, other = pub + p, priv + pv, other + o
                        time.sleep(0.2)
            except Exception as e:  # noqa: BLE001
                failures.append("{}/{}: {}".format(st_name, dt_name,
                                                   str(e)[:80]))
                continue
            counted = pub + priv + other
            entry = {"public": pub, "private": priv, "total": pub + priv}
            if other:
                entry["other_type"] = other
            if expected is not None and counted != expected:
                entry["count_mismatch"] = "counted {} vs site total {}".format(
                    counted, expected)
            st_doc[dt_name] = entry
            n_districts += 1
            time.sleep(0.2)

        if st_doc:
            docs[slug(st_name)] = {
                "state": st_name, "state_census_code": st_code,
                "districts": st_doc, "district_count": len(st_doc),
                "state_public_total": sum(d["public"] for d in st_doc.values()),
                "state_private_total": sum(d["private"] for d in st_doc.values()),
                "source_id": "pmjay_hospitals",
                "updated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
            h.update(json.dumps(docs[slug(st_name)]["districts"],
                                sort_keys=True).encode())
        log.info("pmjay %s: %d districts done", st_name, len(st_doc))

    ok_states = len(docs)
    if not limit and ok_states < MIN_OK_STATES:
        raise ValueError("VERIFY FAIL pmjay: only {} states OK (need >= {}). "
                         "Failures: {}".format(ok_states, MIN_OK_STATES,
                                               "; ".join(failures[:10])))

    with open(out_dir / "parsed_counts.json", "w") as f:
        json.dump(docs, f, indent=1)

    docs["_summary"] = {
        "states_ok": ok_states, "districts_done": n_districts,
        "failures": failures[:50], "subset_run": bool(limit),
        "source_id": "pmjay_hospitals",
        "updated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    content_hash = h.hexdigest()
    note = "{} states, {} districts; public/private counts parsed".format(
        ok_states, n_districts)
    if failures:
        note += " | {} failures (first: {})".format(len(failures), failures[0])
    if limit:
        note = "SUBSET({}) ".format(limit) + note
    return {"rows": n_districts, "raw_path": out_dir,
            "content_hash": content_hash,
            "unchanged": bool(prev_hash and content_hash == prev_hash),
            "agg": {"pmjay_hospitals": docs}, "verify_note": note}
