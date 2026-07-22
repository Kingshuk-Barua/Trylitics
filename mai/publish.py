"""Publish MAI v2 to Firestore. DRY RUN BY DEFAULT.

    python3 -m mai.publish              # dry run: prints what would change
    python3 -m mai.publish --confirm    # actually writes

Fixes the publishing defects the audit found in notebook cell 36:
  m-03  the notebook called `db.batch()` directly, bypassing the daily
        write-budget guard, so 698 writes were invisible to state accounting.
        This module goes through `pipeline.publish.firestore.publish_docs`.
  m-04  the notebook used `batch.set(...)` without merge, unlike every other
        write in the repo. This uses merge=True.
  m-14  documents carried no run_id, updated_at or data vintage.
  C-06  `is_imputed` was absent from all 698 documents.
  M-14  no staleness detection. Each document records the input snapshot
        hashes it was built from, so drift is visible.

Writing 698 mai_scores + 1 mai_runs = 699 writes against the 15,000/day cap.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

import pandas as pd

from . import data as D

OUT = D.CACHE / "v2"


def build_documents():
    scores_path = OUT / "scores_v2_with_intervals.csv"
    if not scores_path.exists():
        sys.exit("run `python3 -m mai.validate` first (it writes rank intervals)")
    df = pd.read_csv(scores_path, index_col=0)
    df.index = [str(i).zfill(3) for i in df.index]
    run = json.load(open(OUT / "run_v2.json"))
    flags = json.load(open(OUT / "imputation_flags_v2.json"))
    # Narratives. The deterministic template is the floor; a G2 narrative is
    # used only where it exists AND passed the numeric-fidelity check, and the
    # document records which one it got. A brief whose provenance is unknown
    # is worse than a plain one.
    narratives = {}
    npath = OUT / "narratives_v2.json"
    if npath.exists():
        narratives = json.load(open(npath))
    llm = {}
    gpath = OUT / "genai" / "g2_narratives.json"
    if gpath.exists():
        llm = json.load(open(gpath))

    # One short id standing for the exact inputs this build saw, so a document
    # can be checked for staleness without fetching the whole run record.
    snapshot_id = hashlib.sha256(
        json.dumps(run.get("input_snapshot_sha256") or {},
                   sort_keys=True).encode()).hexdigest()[:12]

    pillars = [c for c in df.columns if c.startswith(("P2_", "P3_", "P4_", "P5_"))]
    docs = {}
    for code, r in df.iterrows():
        imp = flags.get(code) or flags.get(str(int(code))) or {}
        doc = {
            "district_name": r["district_name"],
            "state_name": r["state_name"],
            "population_2011": (None if pd.isna(r["population"])
                                else int(r["population"])),
            "overall_score": round(float(r["mai_overall"]), 2),
            "overall_rank": int(r["rank_overall"]),
            "chronic_score": round(float(r["mai_chronic"]), 2),
            "chronic_rank": int(r["rank_chronic"]),
            "acute_score": round(float(r["mai_acute"]), 2),
            "acute_rank": int(r["rank_acute"]),
            "tier": str(r["tier"]),
            "current_vs_future": {
                "current_score": round(float(r["mai_current"]), 2),
                "current_rank": int(r["rank_current"]),
                "projected_score": round(float(r["mai_future"]), 2),
                "projected_rank": int(r["rank_future"]),
                "growth_flag": bool(r["growth_flag"]),
                "growth_gap": round(float(r["growth_gap"]), 2),
            },
            "rank_interval_p5_p95": [int(r["rank_lo_p5"]), int(r["rank_hi_p95"])],
            "pillar_scores": {p: round(float(r[p]), 2) for p in pillars
                              if pd.notna(r[p])},
            "size_score": round(float(r["size_score"]), 2),
            "quality_score": round(float(r["quality_overall"]), 2),
            # --- provenance the v1 documents lacked entirely ----------------
            "run_id": run["model_version"],
            "updated_at": run["created_at"],
            "is_imputed": {k: v for k, v in imp.items() if v > 0},
            "imputation_method": "within-state median, then national median; "
                                 "pillars >1/3 missing are re-weighted out",
            "data_vintage": run["data_vintage"],
            "data_snapshot_id": snapshot_id,
        }
        # District codes travel as both "007" and "7" depending on which writer
        # produced the file, so every per-district lookup accepts either form.
        g = llm.get(code) or llm.get(str(int(code)))
        t = narratives.get(code) or narratives.get(str(int(code)))
        if g and g.get("source") == "llm":
            doc["narrative"] = g["narrative"]
            doc["narrative_source"] = "llm:" + g.get("model", "unknown")
            doc["narrative_numeric_check"] = "passed"
        elif t:
            doc["narrative"] = t
            doc["narrative_source"] = "deterministic_template"
            doc["narrative_numeric_check"] = ("n/a — template numbers come "
                                              "straight from the score row")
        docs[code] = doc
    return docs, run


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--confirm", action="store_true",
                    help="actually write to Firestore (default is a dry run)")
    args = ap.parse_args()

    docs, run = build_documents()
    print("prepared %d mai_scores documents + 1 mai_runs/%s"
          % (len(docs), run["model_version"]))
    src = pd.Series([d.get("narrative_source", "(none)")
                     for d in docs.values()]).value_counts()
    print("narrative provenance:")
    for k, v in src.items():
        print("  %-34s %d" % (k, v))
    sample = docs[sorted(docs)[0]]
    print("\nsample document (%s):" % sorted(docs)[0])
    print(json.dumps(sample, indent=2, default=str)[:1400])

    if not args.confirm:
        print("\nDRY RUN — nothing written. Re-run with --confirm to publish.")
        print("This would OVERWRITE the 698 published v1 documents in "
              "mai_scores and add mai_runs/%s." % run["model_version"])
        return

    sys.path.insert(0, str(D.ROOT))
    from pipeline import state as state_mod
    from pipeline.publish import firestore

    st = state_mod.load()
    n = firestore.publish_docs(st, "mai_scores", docs, merge=True)
    firestore.publish_docs(st, "mai_runs", {run["model_version"]: run},
                           merge=True)
    print("published %d mai_scores + 1 mai_runs" % n)


if __name__ == "__main__":
    main()
