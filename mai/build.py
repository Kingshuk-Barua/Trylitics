"""Build MAI v2 end to end. Produces the scores, the run record and the audit
artefacts, and writes them to analysis/audit/_cache/v2/.

    python3 -m mai.build

Read-only with respect to Firestore. Publishing is a separate, explicit step
(`python3 -m mai.publish --confirm`).
"""
import hashlib
import json
import platform
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from . import features as F
from . import impute as IM
from . import index as IX
from . import data as D

OUT = D.CACHE / "v2"
MODEL_VERSION = "mai_v2_2026-07-21"
SEED = 42

DATA_VINTAGE = {
    "census_pca": "2011 (population, urban share, 0-6 share)",
    "secc": "2011 (income, deprivation, assets)",
    "district_spine": "2017 (NFHS-5 sample design)",
    "nfhs5_levels": "2019-21",
    "nfhs_momentum": "2014-15 -> 2019-20 deltas",
    "nfhs5_factsheet": "2019-21",
    "tb_live": "current year to date (Ni-kshay)",
    "pmjay_hospitals": "current (empanelment snapshot)",
    "note": "Levels are fused across vintages. Rank normalisation is used "
            "precisely because district ORDERING is stable across this span "
            "while absolute levels are not (audit M-13).",
}


def _git_sha():
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=D.ROOT,
            stderr=subprocess.DEVNULL).decode().strip()
    except Exception:                                    # noqa: BLE001
        return None


def _snapshot_hashes():
    out = {}
    for p in sorted(D.CACHE.glob("*.pkl")):
        h = hashlib.sha256(p.read_bytes()).hexdigest()[:16]
        out[p.stem] = h
    return out


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    feat, scored, dim, prov = F.build()

    directions = {}
    for fields in F.PILLARS.values():
        directions.update(fields)
    directions.update(F.SIZE)

    indicators = [f for f in F.ALL_INDICATORS if f in scored.columns]
    kept, cov_report = IM.coverage_gate(scored, indicators)
    dropped = [f for f in indicators if f not in kept]

    pillars_kept = {p: {f: d for f, d in fields.items() if f in kept}
                    for p, fields in F.PILLARS.items()}
    pillars_kept = {p: f for p, f in pillars_kept.items() if f}

    # size inputs are not optional — they are imputed but never gated away
    size_cols = [c for c in F.SIZE if c in scored.columns]
    X = scored[kept + size_cols].copy()
    Xi, provenance, pillar_missing, pillar_blocked = IM.impute(
        X, scored["state_name"], pillars_kept)

    # The <1/3 rule (C-06): a district missing more than a third of a pillar's
    # indicators has that pillar's weight re-allocated across its remaining
    # pillars rather than the pillar being fabricated from state medians.
    blocked_any = int(pillar_blocked.values.sum())
    scores, PS, S = IX.build_indices(Xi, directions, method="rank",
                                     blocked=pillar_blocked)
    scores = IX.add_ranks_and_tiers(scores, PS)

    meta = scored[["district_name", "state_name"]].copy()
    meta["population"] = scored["population"]

    imp_summary = IM.imputation_summary(provenance, pillars_kept)
    flags = IM.per_district_flags(provenance, pillars_kept)

    run = {
        "model_version": MODEL_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "git_sha": _git_sha(),
        "python": platform.python_version(),
        "seed": SEED,
        "method": (
            "rank-percentile normalisation (direction-signed) -> pillar means "
            "-> quality composite (weighted arithmetic) -> "
            "MAI = 100 * size^alpha * quality^(1-alpha), alpha=%.2f. "
            "Size = 0.75*rank(population) + 0.25*rank(urban_share). "
            "No winsorisation: ranks are invariant to monotone transforms."
            % IX.ALPHA),
        "alpha": IX.ALPHA,
        "alpha_future": IX.ALPHA_FUTURE,
        "quality_weights": IX.W_QUALITY,
        "index_pillars": IX.INDEX_PILLARS,
        "indicators_kept": kept,
        "indicators_dropped_below_coverage": dropped,
        "indicator_directions": {f: directions[f] for f in kept + size_cols},
        "pillar_composition": {p: sorted(f) for p, f in pillars_kept.items()},
        "n_districts": int(len(scores)),
        "n_indicators": len(kept),
        "imputation": imp_summary,
        "pillar_blocked_cells": blocked_any,
        "nfhs4_sentinel_fields": prov["nfhs4_sentinel_fields"],
        "n_nfhs4_sentinel_fields": prov["n_sentinel_fields"],
        "pca_repaired": prov["pca_repaired"],
        "secc_joined_districts": prov["secc_joined"],
        "data_vintage": DATA_VINTAGE,
        "input_snapshot_sha256": _snapshot_hashes(),
    }

    scores.join(meta).join(PS.round(3)).to_csv(OUT / "scores_v2.csv")
    PS.to_csv(OUT / "pillar_scores_v2.csv")
    Xi.to_csv(OUT / "features_imputed_v2.csv")
    provenance.to_csv(OUT / "provenance_v2.csv")
    cov_report.to_csv(OUT / "coverage_report_v2.csv")
    with open(OUT / "run_v2.json", "w") as f:
        json.dump(run, f, indent=2, default=str)
    with open(OUT / "imputation_flags_v2.json", "w") as f:
        json.dump(flags, f)
    for name in ("tb_audit", "pm_audit", "fs_audit"):
        prov[name].to_csv(OUT / (name + "_v2.csv"), index=False)

    # crosswalk review file (M-17): every non-exact decision, for human review
    review = pd.concat([prov["tb_audit"].assign(source="tb_live"),
                        prov["pm_audit"].assign(source="pmjay"),
                        prov["fs_audit"].assign(source="nfhs5_factsheet")],
                       ignore_index=True)
    review[review["category"] != "EXACT"].to_csv(
        OUT / "crosswalk_review_v2.csv", index=False)

    print("MAI v2 built -> %s" % OUT)
    print("  districts scored        : %d" % len(scores))
    print("  indicators kept         : %d  (dropped %d: %s)"
          % (len(kept), len(dropped), dropped))
    print("  SECC joined             : %d districts" % prov["secc_joined"])
    print("  PCA repaired            : %s" % prov["pca_repaired"])
    print("  NFHS-4 sentinel fields  : %d (v1 hard-coded 2)"
          % prov["n_sentinel_fields"])
    print("  imputed cells           : %.2f%%" % imp_summary["imputed_pct"])
    print("  per-pillar imputed      : %s" % imp_summary["per_pillar_imputed_pct"])
    print("  crosswalk non-exact rows: %d (written to crosswalk_review_v2.csv)"
          % int((review["category"] != "EXACT").sum()))
    print("  by category             : %s"
          % review["category"].value_counts().to_dict())
    return scores, PS, Xi, meta, run, prov


if __name__ == "__main__":
    main()
