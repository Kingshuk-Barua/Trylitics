"""data.gov.in fetcher — step D (NFHS-5 factsheet, 707 districts x 109 cols)."""
import hashlib
import json
from datetime import datetime, timezone

from .. import config
from ..http_client import get_json
from ..transform import aggregate


def fetch(source_id, cfg, session, prev_hash):
    key = config.data_gov_in_api_key()
    url = ("https://api.data.gov.in/resource/{}?api-key={}&format=json"
           "&limit=1000".format(cfg["resource_id"], key))
    d = get_json(session, url)

    total = d.get("total")
    recs = d.get("records", [])
    lo, hi = cfg["expect_total"]
    if total is None or not (lo <= int(total) <= hi):
        raise ValueError("VERIFY FAIL {}: total={} outside [{}, {}] "
                         "(status={})".format(source_id, total, lo, hi,
                                              d.get("status")))
    if len(recs) < lo:
        raise ValueError("VERIFY FAIL {}: only {} records returned".format(
            source_id, len(recs)))

    content_hash = hashlib.sha256(
        json.dumps(recs, sort_keys=True).encode()).hexdigest()
    if prev_hash and content_hash == prev_hash:
        return {"rows": len(recs), "raw_path": None, "content_hash": content_hash,
                "unchanged": True, "agg": aggregate.agg_datagovin_nfhs5(recs),
                "verify_note": "unchanged (hash match); total={}".format(total)}

    out_dir = config.RAW_DIR / cfg["raw_name"] / "ingest_{}".format(
        datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S"))
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "nfhs5_factsheet_707.json"
    with open(out, "w") as f:
        json.dump(d, f)  # verbatim

    return {"rows": len(recs), "raw_path": out_dir, "content_hash": content_hash,
            "unchanged": False, "agg": aggregate.agg_datagovin_nfhs5(recs),
            "verify_note": "total={} records={} (expected 707)".format(
                total, len(recs))}
