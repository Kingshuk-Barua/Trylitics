"""geoBoundaries fetcher — step E (India ADM2 district polygons)."""
import hashlib
import json
import shutil
from datetime import datetime, timezone

from .. import config
from ..http_client import get_json


def fetch(source_id, cfg, session, prev_hash):
    meta = get_json(session, cfg["meta_url"])
    gj_url = meta.get("gjDownloadURL")
    if not gj_url:
        raise ValueError("VERIFY FAIL {}: no gjDownloadURL in metadata "
                         "response".format(source_id))

    r = session.get(gj_url, timeout=300)
    r.raise_for_status()
    content = r.content
    gj = json.loads(content)
    n = len(gj.get("features", []))
    lo, hi = cfg["expect_features"]
    if not (lo <= n <= hi):
        raise ValueError("VERIFY FAIL {}: {} features outside [{}, {}]".format(
            source_id, n, lo, hi))
    props = gj["features"][0].get("properties", {})
    for fld in ("shapeName", "shapeID"):
        if fld not in props:
            raise ValueError("VERIFY FAIL {}: feature missing {}".format(
                source_id, fld))

    content_hash = hashlib.sha256(content).hexdigest()
    stable = config.RAW_DIR / cfg["raw_name"] / "india_adm2.geojson"
    if prev_hash and content_hash == prev_hash and stable.exists():
        return {"rows": n, "raw_path": None, "content_hash": content_hash,
                "unchanged": True, "agg": None,
                "verify_note": "unchanged; {} features".format(n)}

    out_dir = config.RAW_DIR / cfg["raw_name"] / "ingest_{}".format(
        datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S"))
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_dir / "metadata.json", "w") as f:
        json.dump(meta, f, indent=2)
    gj_path = out_dir / "india_adm2.geojson"
    with open(gj_path, "wb") as f:
        f.write(content)
    # stable path for the app build / Hosting public/ (checklist step E path)
    shutil.copyfile(gj_path, stable)

    return {"rows": n, "raw_path": out_dir, "content_hash": content_hash,
            "unchanged": False, "agg": None,
            "verify_note": "{} district features; shapeName/shapeID present; "
                           "stable copy at {}".format(n, stable)}
