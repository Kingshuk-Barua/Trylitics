"""SHRUG fetcher — step I (optional; manual table pick).

Dev Data Lab's download page requires a human to choose tables; direct S3
zip links go into config.SOURCES['shrug']['download_urls']. Until then the
step reports skipped — never guessed URLs. License CC BY-NC-SA: academic OK,
cite Dev Data Lab.
"""
import hashlib
from datetime import datetime, timezone

from .. import config


def fetch(source_id, cfg, session, prev_hash):
    urls = cfg.get("download_urls") or []
    if not urls:
        return {"skipped": True,
                "why": ("manual step: pick tables at "
                        "https://www.devdatalab.org/shrug_download/ and paste "
                        "the direct zip URLs into config.SOURCES['shrug']"
                        "['download_urls']")}

    out_dir = config.RAW_DIR / cfg["raw_name"] / "ingest_{}".format(
        datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S"))
    out_dir.mkdir(parents=True, exist_ok=True)
    h = hashlib.sha256()
    saved = 0
    for url in urls:
        name = url.rstrip("/").split("/")[-1] or "download.zip"
        r = session.get(url, timeout=600, stream=True)
        r.raise_for_status()
        with open(out_dir / name, "wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)
                h.update(chunk)
        saved += 1
    return {"rows": saved, "raw_path": out_dir, "content_hash": h.hexdigest(),
            "unchanged": False, "agg": None,
            "verify_note": "{} zip(s) downloaded (raw only; local analysis "
                           "layer)".format(saved)}
