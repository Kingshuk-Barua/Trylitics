"""Data access for the v2 model.

Reads the local Firestore snapshot produced by
`analysis/audit/00_pull_firestore.py`, applies the two source-level repairs the
audit identified, and builds the district spine.

Repairs applied here (they are also fixed upstream in
`pipeline/transform/aggregate.py`, but the published Firestore documents still
carry the v1 values until the pipeline is re-run, so the model must not depend
on that having happened):

  R-01 / C-04  census_pca populations. The published docs were built with the
               broken level-preference rule. Where a corrected local
               re-aggregation exists (`analysis/audit/_cache/pca_fixed.json`,
               produced by `mai/fix_pca.py` from the raw CKAN pull) it is used;
               otherwise the published values are used and flagged.
  R-02 / M-11  SECC codes are unpadded ('2' vs '002'). Zero-padding joins
               631/631 documents with zero orphans — verified.
"""
import json
import pickle
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "analysis" / "audit" / "_cache"

CENSUS_2011_TOTAL = 1210854977


def load(name):
    with open(CACHE / (name + ".pkl"), "rb") as f:
        return pickle.load(f)


def load_secc_repaired():
    """SECC keyed by ZERO-PADDED district code (audit R-02/M-11).

    v1 joined on the raw key and lost 97 of 631 documents, dropping every
    income and deprivation indicator below the 80% coverage gate and leaving
    the affordability pillar with no ability-to-pay variable at all.
    """
    raw = load("secc")
    out = {}
    for code, doc in raw.items():
        out[str(code).zfill(3)] = doc
    assert len(out) == len(raw), "zero-padding collided two SECC codes"
    return out


def load_pca_repaired():
    """census_pca with corrected populations where available (R-01/C-04)."""
    pca = {k: dict(v) for k, v in load("census_pca").items()}
    fixed_path = CACHE / "pca_fixed.json"
    if not fixed_path.exists():
        for d in pca.values():
            d.setdefault("population_source", "idp_pca_mirror_UNREPAIRED")
        return pca, False
    fixed = json.load(open(fixed_path))
    for code, vals in fixed.items():
        doc = pca.setdefault(code, {})
        doc.update(vals)
    return pca, True


def build_spine(indicators, pca):
    """The district frame. NFHS districts are the scored set; census_pca may
    carry extras, which are retained in the frame but not scored."""
    from .crosswalk import norm_name, norm_state
    rows = {}
    for code, d in indicators.items():
        rows[code] = {"district_code": code, "district_name": d.get("district_name"),
                      "state_name": d.get("state_name"), "in_nfhs": True}
    for code, d in pca.items():
        r = rows.setdefault(code, {"district_code": code, "in_nfhs": False})
        r.setdefault("district_name", d.get("district_name"))
        r.setdefault("state_name", d.get("state_name"))
    dim = pd.DataFrame(rows.values())
    dim["in_pca"] = dim["district_code"].isin(pca)
    dim["nname"] = dim["district_name"].map(norm_name)
    dim["nstate"] = dim["state_name"].map(norm_state)
    return dim


def spine_names_by_state(dim):
    return {st: set(g["nname"]) for st, g in dim.groupby("nstate")}


def code_lookup(dim):
    """(nstate, nname) -> district_code"""
    return {(r.nstate, r.nname): r.district_code for r in dim.itertuples()}
