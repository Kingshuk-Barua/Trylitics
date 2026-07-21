"""DHS API fetcher — step J (STATE-level anchor only; India has no district
rows in the DHS API — verified limitation, see credentials JSON)."""
import hashlib
import json
from datetime import datetime, timezone

from .. import config
from ..http_client import get_json


def fetch(source_id, cfg, session, prev_hash):
    url = cfg["url"]
    d = get_json(session, url)
    rows = d.get("Data", [])
    record_count = d.get("RecordCount", len(rows))
    total_pages = d.get("TotalPages", 1)
    if not rows:
        raise ValueError("VERIFY FAIL dhs: no Data rows (RecordCount={})".format(
            record_count))

    all_pages = [d]
    for page in range(2, int(total_pages) + 1):
        all_pages.append(get_json(session, url + "&page={}".format(page)))
        rows = rows + all_pages[-1].get("Data", [])

    content_hash = hashlib.sha256(
        json.dumps(rows, sort_keys=True).encode()).hexdigest()
    if prev_hash and content_hash == prev_hash:
        return {"rows": len(rows), "raw_path": None,
                "content_hash": content_hash, "unchanged": True, "agg": None,
                "verify_note": "unchanged; {} state-level rows".format(len(rows))}

    out_dir = config.RAW_DIR / cfg["raw_name"] / "ingest_{}".format(
        datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S"))
    out_dir.mkdir(parents=True, exist_ok=True)
    for i, page in enumerate(all_pages, 1):
        with open(out_dir / "nfhs5_state_p{}.json".format(i), "w") as f:
            json.dump(page, f)  # verbatim

    return {"rows": len(rows), "raw_path": out_dir,
            "content_hash": content_hash, "unchanged": False, "agg": None,
            "verify_note": "{} rows across {} page(s); STATE-level anchor "
                           "only".format(len(rows), total_pages)}
