"""Read-only pull of every Firestore collection into a local pickle cache.

Audit support script (docs/MAI_AUDIT_FINDINGS.md). READ ONLY — this script
never calls set/update/delete. Run from the repo root:

    python3 analysis/audit/00_pull_firestore.py

Writes analysis/audit/_cache/<collection>.pkl and a manifest.json.
"""
import json
import pickle
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
CACHE = Path(__file__).resolve().parent / "_cache"
CACHE.mkdir(exist_ok=True)

from pipeline import config  # noqa: E402  (uses the repo's own credential loader)

import firebase_admin  # noqa: E402
from firebase_admin import credentials, firestore  # noqa: E402

if not firebase_admin._apps:
    firebase_admin.initialize_app(
        credentials.Certificate(config.firebase_service_account()))
db = firestore.client()

# Discover rather than assume: list_collections() surfaces anything the
# schema docs forgot to mention.
names = sorted(c.id for c in db.collections())
print("collections found:", names)

manifest = {}
for name in names:
    docs = {d.id: d.to_dict() for d in db.collection(name).stream()}
    with open(CACHE / (name + ".pkl"), "wb") as f:
        pickle.dump(docs, f)
    manifest[name] = len(docs)
    print("  %-24s %5d docs" % (name, len(docs)))

with open(CACHE / "manifest.json", "w") as f:
    json.dump(manifest, f, indent=2)
print("cached ->", CACHE)
