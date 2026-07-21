"""Fetcher registry: source `kind` -> fetch callable.

Every fetcher has signature  fetch(source_id, cfg, session, prev_hash) -> dict:
    {
      "rows": int,              # rows/features fetched (None if n/a)
      "raw_path": str,          # directory or file where raw was saved
      "content_hash": str,      # sha256 of the payload (for unchanged-detection)
      "unchanged": bool,        # True if identical to previous successful run
      "verify_note": str,       # human-readable verification summary
      "agg": dict or None,      # {collection: {doc_id: doc}} for Firestore
    }
A fetcher must RAISE on any failure (bad HTTP, verification out of bounds…) —
run.py records the exact error into the state table. Never fake data.
"""
from . import idp_ckan, datagovin, geoboundaries, nikshay, pmjay, shrug, dhs

FETCHERS = {
    "ckan": idp_ckan.fetch,
    "datagovin": datagovin.fetch,
    "geoboundaries": geoboundaries.fetch,
    "nikshay": nikshay.fetch,
    "pmjay": pmjay.fetch,
    "shrug": shrug.fetch,
    "dhs": dhs.fetch,
}
