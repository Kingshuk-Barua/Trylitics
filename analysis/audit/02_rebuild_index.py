"""Faithful re-implementation of notebooks/MAI_analysis.ipynb Phases 1-3 from
the cached Firestore snapshot, so the composite can be stressed without
touching Firestore. Exports the rebuilt matrices to _cache/*.parquet-ish CSVs.

Every constant here is copied verbatim from the notebook. If this script
reproduces the published mai_scores to within rounding, the rebuild is
faithful and every downstream audit number is trustworthy.

    python3 analysis/audit/02_rebuild_index.py
"""
import pickle
import re
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

CACHE = Path(__file__).resolve().parent / "_cache"
RNG = np.random.RandomState(42)


def load(name):
    with open(CACHE / (name + ".pkl"), "rb") as f:
        return pickle.load(f)


fs_ind = load("district_indicators")
fs_pca = load("census_pca")
fs_secc = load("secc")
fs_tb = load("tb_live")
fs_pmjay = load("pmjay_hospitals")
fs_mai = load("mai_scores")


# ---------------------------------------------------------------- crosswalk
def norm_name(s):
    s = str(s).lower().strip().replace("&", "and")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", s)).strip()


def norm_state(s):
    x = norm_name(s)
    return {
        "nct of delhi": "delhi", "delhi ut": "delhi",
        "jammu and kashmir ut": "jammu and kashmir",
        "andaman and nicobar island": "andaman and nicobar islands",
        "pondicherry": "puducherry", "orissa": "odisha",
        "chattisgarh": "chhattisgarh", "uttaranchal": "uttarakhand",
    }.get(x, x)


spine = {}
for code_, d in fs_ind.items():
    spine[code_] = {"district_code": code_, "district_name": d.get("district_name"),
                    "state_name": d.get("state_name"), "in_nfhs": True}
for code_, d in fs_pca.items():
    r = spine.setdefault(code_, {"district_code": code_, "in_nfhs": False})
    r.setdefault("district_name", d.get("district_name"))
    r.setdefault("state_name", d.get("state_name"))
dim = pd.DataFrame(spine.values())
dim["in_pca"] = dim["district_code"].isin(fs_pca.keys())
dim["in_secc"] = dim["district_code"].isin(fs_secc.keys())
dim["nname"] = dim["district_name"].map(norm_name)
dim["nstate"] = dim["state_name"].map(norm_state)

from difflib import get_close_matches  # noqa: E402


def match_named_source(state_docs, merge_mc=False):
    matched, unmatched, fuzzy = {}, [], []
    by_state = {st: g for st, g in dim.groupby("nstate")}
    for sid, doc in state_docs.items():
        if sid.startswith("_"):
            continue
        st = norm_state(doc.get("state", sid.replace("_", " ")))
        g = by_state.get(st)
        if g is None:
            unmatched.append((doc.get("state"), "<whole state>", "state not in spine"))
            continue
        rows = {}
        for name, vals in doc["districts"].items():
            base = (re.sub(r"\s+(mc|municipal corporation|corporation|mcorp)$", "",
                           norm_name(name)) if merge_mc else norm_name(name))
            rows.setdefault(base, []).append(vals)
        for base, vlist in rows.items():
            agg_ = {}
            for v in vlist:
                for k, x in v.items():
                    if isinstance(x, (int, float)):
                        agg_[k] = agg_.get(k, 0) + x
            hit = g[g["nname"] == base]
            if hit.empty:
                cand = get_close_matches(base, list(g["nname"]), n=1, cutoff=0.85)
                if cand:
                    hit = g[g["nname"] == cand[0]]
                    fuzzy.append((doc.get("state"), base, cand[0]))
            if hit.empty:
                unmatched.append((doc.get("state"), base, "no name match"))
            else:
                codek = hit.iloc[0]["district_code"]
                prev = matched.get(codek, {})
                for k, x in agg_.items():
                    prev[k] = prev.get(k, 0) + x
                matched[codek] = prev
    return matched, unmatched, fuzzy


tb_by_code, tb_unmatched, tb_fuzzy = match_named_source(fs_tb, merge_mc=True)
pm_by_code, pm_unmatched, pm_fuzzy = match_named_source(fs_pmjay, merge_mc=False)

# ------------------------------------------------------------ feature matrix
NF5, NF4 = "2019_20", "2014_15"
NFHS_MAP = {
    "P2c": [("wom_bld_sugar_high", +1), ("men_bld_sugar_high", +1),
            ("wom_bp_ele_med", +1), ("men_bp_ele_med", +1),
            ("wom_obese", +1), ("wom_wh_ratio", +1),
            ("tobaco_men_15", +1), ("alcohol_men_15", +1)],
    "P2a": [("child_6_59_anemic", +1), ("wom_15_49_anaemic", +1),
            ("cd_ari_2wks", +1), ("cd_drh_2wks", +1),
            ("child_5_stunted", +1), ("child_5_underweight", +1),
            ("pop_hh_dw", -1), ("pop_hh_sf", -1)],
    "P3": [("dc_insti_births", +1), ("births_skill_personnel", +1),
           ("cv_12_23_full_vacc", +1), ("mc_anc_4", +1),
           ("cv_12_23_vac_private", +1)],
    "P4": [("hh_hlth_ins_fs", +1), ("fem_literacy", +1),
           ("pop_hh_elec", +1), ("hh_fuel_cooking", +1),
           ("avg_delivery_exp_phf", +1)],
}
MOMENTUM_FIELDS = [("wom_bld_sugar_high", +1), ("wom_bp_ele_med", +1),
                   ("wom_obese", +1), ("hh_hlth_ins_fs", +1),
                   ("dc_insti_births", +1)]
NFHS4_ZERO_MEANS_MISSING = {"wom_bld_sugar_high", "wom_bp_ele_med"}

rows = []
for _, r in dim.iterrows():
    c = r["district_code"]
    row = {"district_code": c, "district_name": r["district_name"],
           "state_name": r["state_name"]}
    nf = (fs_ind.get(c) or {}).get("nfhs", {})
    f5, f4 = nf.get(NF5, {}), nf.get(NF4, {})
    for _p, fields in NFHS_MAP.items():
        for f, _ in fields:
            row[f] = f5.get(f)
    for f, _ in MOMENTUM_FIELDS:
        v5, v4 = f5.get(f), f4.get(f)
        if f in NFHS4_ZERO_MEANS_MISSING and v4 == 0:
            v4 = None
        row["d_" + f] = (v5 - v4) if (v5 is not None and v4 is not None) else None
    pca = fs_pca.get(c) or {}
    pop = pca.get("population_2011_total")
    row["population"] = pop
    urb = pca.get("pop_urban_total")
    row["urban_share"] = (urb / pop * 100) if (urb and pop) else None
    row["pop_below_15"] = f5.get("pop_below_15")
    secc = (fs_secc.get(c) or {}).get("categories", {}).get("all", {})
    th = secc.get("tot_hh")
    if th:
        row["inc_gt10k_share"] = (secc.get("mon_inc_gt_10k") or 0) / th * 100
        row["deprivation_share"] = (secc.get("hh_considered_deprivation") or 0) / th * 100
        row["vehicle_share"] = (secc.get("own_motor_vehicle") or 0) / th * 100
    tb = tb_by_code.get(c) or {}
    tb_tot = (tb.get("public") or 0) + (tb.get("private") or 0)
    if pop and tb_tot:
        row["tb_per_lakh"] = tb_tot / pop * 100000
        row["tb_private_share"] = (tb.get("private") or 0) / tb_tot * 100
    pm = pm_by_code.get(c) or {}
    pm_tot = (pm.get("public") or 0) + (pm.get("private") or 0)
    if pop and pm_tot:
        row["hosp_per_lakh"] = pm_tot / pop * 100000
        row["hosp_private_per_lakh"] = (pm.get("private") or 0) / pop * 100000
    rows.append(row)
feat = pd.DataFrame(rows).set_index("district_code")

PILLARS = {
    "P1_scale": {"log_population": +1, "urban_share": +1, "pop_below_15": +1},
    "P2_chronic": dict(NFHS_MAP["P2c"]),
    "P2_acute": dict(list(dict(NFHS_MAP["P2a"]).items()) + [("tb_per_lakh", +1)]),
    "P3_access": dict(list(dict(NFHS_MAP["P3"]).items())
                      + [("hosp_per_lakh", +1), ("hosp_private_per_lakh", +1)]),
    "P4_afford": dict(list(dict(NFHS_MAP["P4"]).items())
                      + [("inc_gt10k_share", +1), ("deprivation_share", -1),
                         ("vehicle_share", +1)]),
    "P5_momentum": {"d_" + f: d for f, d in MOMENTUM_FIELDS},
}
feat["log_population"] = np.log10(feat["population"].where(feat["population"] > 0))
ALL_IND = [f for p in PILLARS.values() for f in p]

base = feat[feat.index.isin(fs_ind.keys())]
coverage = base[ALL_IND].notna().mean().sort_values()
dropped = coverage[coverage < 0.80]
for f in dropped.index:
    for p in PILLARS.values():
        p.pop(f, None)
ALL_IND = [f for p in PILLARS.values() for f in p]

X = base[ALL_IND].copy()
imputed = X.isna()
X = X.groupby(base["state_name"]).transform(lambda s: s.fillna(s.median()))
X = X.fillna(X.median())
meta = base[["district_name", "state_name", "population"]].copy()

# --------------------------------------------------------- composite (Phase 3)
screen = pd.DataFrame([
    {"indicator": f, "skew": stats.skew(X[f].dropna()),
     "kurtosis": stats.kurtosis(X[f].dropna()),
     "winsorize": abs(stats.skew(X[f].dropna())) > 2
                  and stats.kurtosis(X[f].dropna()) > 3.5}
    for f in ALL_IND]).set_index("indicator")

Xw = X.copy()
for f in screen[screen["winsorize"]].index:
    lo, hi = Xw[f].quantile([.025, .975])
    Xw[f] = Xw[f].clip(lo, hi)

DIR = {}
for p, fields in PILLARS.items():
    DIR.update(fields)
N = pd.DataFrame(index=Xw.index)
for f in ALL_IND:
    v = Xw[f]
    n = (v - v.min()) / (v.max() - v.min()) * 100
    N[f] = 100 - n if DIR[f] < 0 else n

pillar_scores = pd.DataFrame({p: N[list(fields)].mean(axis=1)
                              for p, fields in PILLARS.items()})

W_BUSINESS = {"P1_scale": .25, "P2_chronic": .125, "P2_acute": .125,
              "P3_access": .20, "P4_afford": .15, "P5_momentum": .15}


def agg(ps, w, geometric=False):
    wv = np.array([w[c] for c in ps.columns])
    if geometric:
        return np.exp((np.log(ps.clip(lower=1)) * wv).sum(axis=1) / wv.sum())
    return (ps * wv).sum(axis=1) / wv.sum()


wch = {"P1_scale": .25, "P2_chronic": .25, "P3_access": .20,
       "P4_afford": .15, "P5_momentum": .15}
wac = {"P1_scale": .25, "P2_acute": .25, "P3_access": .20,
       "P4_afford": .15, "P5_momentum": .15}
W_FUT = dict(W_BUSINESS)
W_FUT["P5_momentum"] = .30
W_FUT = {k: v / sum(W_FUT.values()) for k, v in W_FUT.items()}

scores = pd.DataFrame(index=pillar_scores.index)
scores["mai_overall"] = agg(pillar_scores, W_BUSINESS)
scores["mai_overall_geom"] = agg(pillar_scores, W_BUSINESS, geometric=True)
scores["mai_chronic"] = agg(pillar_scores[list(wch)], wch)
scores["mai_acute"] = agg(pillar_scores[list(wac)], wac)
scores["mai_current"] = agg(
    pillar_scores[[c for c in pillar_scores if c != "P5_momentum"]],
    {k: v for k, v in W_BUSINESS.items() if k != "P5_momentum"})
scores["mai_future"] = agg(pillar_scores, W_FUT)
for c in ["mai_overall", "mai_chronic", "mai_acute", "mai_current", "mai_future"]:
    scores[c.replace("mai", "rank")] = scores[c].rank(ascending=False).astype(int)
scores["tier"] = pd.qcut(scores["mai_overall"], 4, labels=["D", "C", "B", "A"])

if __name__ == "__main__":
    pub = pd.DataFrame({k: {"pub_overall": v["overall_score"],
                            "pub_chronic": v["chronic_score"],
                            "pub_acute": v["acute_score"],
                            "pub_rank": v["overall_rank"]}
                        for k, v in fs_mai.items()}).T
    chk = scores.join(pub)
    d = (chk["mai_overall"] - chk["pub_overall"]).abs()
    print("REBUILD FIDELITY vs published mai_scores")
    print("  districts compared      :", chk["pub_overall"].notna().sum())
    print("  max |overall delta|     : %.4f" % d.max())
    print("  mean |overall delta|    : %.4f" % d.mean())
    print("  rank Spearman vs published: %.6f"
          % stats.spearmanr(chk["mai_overall"], chk["pub_overall"]).statistic)
    print("  districts w/ |delta|>0.5 :", int((d > 0.5).sum()))
    print("\n  tb_live matched %d / unmatched %d (fuzzy accepts %d)"
          % (len(tb_by_code), len(tb_unmatched), len(tb_fuzzy)))
    print("  pmjay   matched %d / unmatched %d (fuzzy accepts %d)"
          % (len(pm_by_code), len(pm_unmatched), len(pm_fuzzy)))
    print("  indicators kept %d; dropped %s" % (len(ALL_IND), list(dropped.index)))
    print("  imputed cells %d (%.2f%%)"
          % (imputed.values.sum(), imputed.values.sum() / X.size * 100))
