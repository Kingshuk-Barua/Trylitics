"""CKAN datastore fetcher (India Data Portal) — steps A, B, C, F.

Streams pages to disk (HMIS is ~547k rows; never held fully in memory),
verifies totals/fields against config expectations, feeds the streaming
aggregator, and detects unchanged content via sha256.

Config-driven behaviour (see config.SOURCES):
  gzip_pages   pages are written as page_NNNN.json.gz instead of .json
  resume       an interrupted .tmp_ingest is continued instead of wiped.
               Only honoured together with hash_mode="total" (a rolling
               content hash cannot be resumed without re-reading every page).
  hash_mode    "content" (default): sha256 over every page's records.
               "total": sha256 over resource_id + result.total — cheap
               unchanged-detection for huge, effectively-static resources.
"""
import gzip
import hashlib
import json
import logging
import shutil
import time
from datetime import datetime, timezone

from .. import config
from ..http_client import get_json
from ..transform import aggregate

log = logging.getLogger("pipeline.ckan")


def _page_name(page, gz):
    return "page_{:04d}.json{}".format(page, ".gz" if gz else "")


def _open_write(path, gz):
    return gzip.open(path, "wt") if gz else open(path, "w")


def _resume_scan(tmp, gz):
    """Validate an interrupted ingest dir; return usable completed page count.

    The last page on disk is always dropped: the process may have died
    mid-write, and refetching one page (5000 rows) is cheaper than proving
    integrity. Earlier pages were fully written before the next request
    started, so they are trusted.
    """
    suffix = ".json.gz" if gz else ".json"
    pages = sorted(p for p in tmp.iterdir()
                   if p.name.startswith("page_") and p.name.endswith(suffix))
    if not pages:
        return 0
    pages[-1].unlink()
    pages = pages[:-1]
    expected = [_page_name(i, gz) for i in range(len(pages))]
    if [p.name for p in pages] != expected:
        log.warning("resume scan: page files not contiguous — starting fresh")
        for p in pages:
            p.unlink()
        return 0
    return len(pages)


def fetch(source_id, cfg, session, prev_hash):
    rid = cfg["resource_id"]
    gz = bool(cfg.get("gzip_pages"))
    hash_total = cfg.get("hash_mode") == "total"
    can_resume = bool(cfg.get("resume")) and hash_total
    agg = None if cfg.get("raw_only") else aggregate.get_ckan_aggregator(source_id)
    raw_root = config.RAW_DIR / cfg["raw_name"]
    tmp = raw_root / ".tmp_ingest"

    page = 0
    resumed_pages = 0
    if tmp.exists():
        if can_resume and agg is None:
            resumed_pages = _resume_scan(tmp, gz)
            page = resumed_pages
            if resumed_pages:
                log.info("%s: resuming interrupted ingest at page %d "
                         "(offset %d)", source_id, page,
                         page * config.CKAN_PAGE_SIZE)
        else:
            shutil.rmtree(tmp)
    tmp.mkdir(parents=True, exist_ok=True)

    h = hashlib.sha256()
    offset = page * config.CKAN_PAGE_SIZE
    rows = offset  # completed resumed pages are always full pages
    total = None
    while True:
        url = "{}?resource_id={}&limit={}&offset={}".format(
            config.CKAN_BASE, rid, config.CKAN_PAGE_SIZE, offset)
        d = get_json(session, url)
        res = d["result"]
        recs = res.get("records", [])

        if total is None:
            total = res.get("total")
            lo, hi = cfg["expect_total"]
            if total is None or not (lo <= total <= hi):
                shutil.rmtree(tmp)
                raise ValueError(
                    "VERIFY FAIL {}: result.total={} outside expected "
                    "[{}, {}]".format(source_id, total, lo, hi))
            missing = [f for f in cfg.get("required_fields", [])
                       if recs and f not in recs[0]]
            if missing:
                shutil.rmtree(tmp)
                raise ValueError("VERIFY FAIL {}: missing fields {} in first "
                                 "record".format(source_id, missing))
            if hash_total:
                h.update("{}:total={}".format(rid, total).encode())
                if prev_hash and h.hexdigest() == prev_hash and not resumed_pages:
                    # Same total as the last completed ingest — skip the pull.
                    shutil.rmtree(tmp)
                    return {"rows": total, "raw_path": None,
                            "content_hash": prev_hash, "unchanged": True,
                            "agg": None,
                            "verify_note": "unchanged (total={} matches "
                                           "previous ingest)".format(total)}

        if not recs:
            break
        with _open_write(tmp / _page_name(page, gz), gz) as f:
            json.dump(d, f)  # verbatim full response
        if not hash_total:
            h.update(json.dumps(recs, sort_keys=True).encode())
        if agg:
            agg.add(recs)
        rows += len(recs)
        page += 1
        if len(recs) < config.CKAN_PAGE_SIZE:
            break
        offset += config.CKAN_PAGE_SIZE
        time.sleep(0.4)
        if page % 10 == 0:
            log.info("%s: %d/%s rows (%d pages)…", source_id, rows, total, page)

    content_hash = h.hexdigest()
    if not hash_total and prev_hash and content_hash == prev_hash:
        shutil.rmtree(tmp)
        return {"rows": rows, "raw_path": None, "content_hash": content_hash,
                "unchanged": True, "agg": agg.result() if agg else None,
                "verify_note": "unchanged (hash match); total={} rows={}".format(
                    total, rows)}

    final = raw_root / "ingest_{}".format(
        datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S"))
    tmp.rename(final)
    note = "total={}, fetched {} rows in {} pages{}; expected {} OK".format(
        total, rows, page,
        " ({} resumed)".format(resumed_pages) if resumed_pages else "",
        cfg["expect_total"])
    return {"rows": rows, "raw_path": final, "content_hash": content_hash,
            "unchanged": False, "agg": agg.result() if agg else None,
            "verify_note": note}
