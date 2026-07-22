"""Feature matrix for MAI v2.

Changes against v1 (notebook cells 4-10), each tagged with the audit finding:

  C-05/M-17  crosswalk goes through `mai.crosswalk` — explicit alias table,
             parent roll-up for post-2011 splits, sub-district roll-up,
             pro-rata allocation for genuinely ambiguous units, and a written
             review file for every fuzzy accept.
  C-04/R-01  populations come from the corrected PCA re-aggregation.
  M-11/R-02  SECC joins on zero-padded codes, restoring income + deprivation.
  M-04/R-09  age structure enters properly: `pop_below_15` is REMOVED from
             scale and re-enters chronic burden inverted (an older population
             is more chronic-attractive, not less). `pop_0_6_share` carries the
             paediatric/acute segment.
  M-06/R-15  momentum is widened from 3 indicators to a chronic set and an
             acute set, so the therapy indices differ in their forward view.
             The NFHS-4 zero sentinel is detected EMPIRICALLY across all 104
             fields rather than hard-coded for 2 (v1 missed 43 more).
  M-10/R-08  the nfhs5_factsheet is used, but only its clean fields, joined by
             name through the same crosswalk.
  C-06/R-05  imputation enforces the <1/3 rule and records per-cell provenance.
"""
import collections
import json
from pathlib import Path

import numpy as np
import pandas as pd

from . import crosswalk as xw
from . import data as D

NF5, NF4 = "2019_20", "2014_15"
CACHE = D.CACHE


# ---------------------------------------------------------------------------
# NFHS-4 sentinel detection (generalises v1's hard-coded 2-field fix)
# ---------------------------------------------------------------------------
def detect_nfhs4_sentinels(indicators, min_zero_share=0.90):
    """Fields where NFHS-4 stores 'not collected' as 0.0.

    v1 hard-coded {wom_bld_sugar_high, wom_bp_ele_med}. Measured across all
    104 fields, 45 fields are exactly 0.0 for >=90% of paired districts —
    blood sugar and BP for BOTH sexes, tobacco, alcohol, waist-hip ratio, the
    three cancers, and more. A delta against that sentinel equals the NFHS-5
    level and would smuggle the level into the momentum pillar.
    """
    zeros, present = collections.Counter(), collections.Counter()
    for d in indicators.values():
        a = (d.get("nfhs") or {}).get(NF4) or {}
        for k, v in a.items():
            if v is None:
                continue
            present[k] += 1
            if v == 0:
                zeros[k] += 1
    return {k for k, n in present.items()
            if n and zeros[k] / n >= min_zero_share}


# ---------------------------------------------------------------------------
# Named-source matching through the crosswalk
# ---------------------------------------------------------------------------
def match_named_source(state_docs, dim, names_by_state, code_of, value_key=None):
    """Resolve a {state_doc_id: {districts: {label: values}}} source onto the
    spine. Returns (by_code, audit_rows)."""
    by_code = collections.defaultdict(lambda: collections.Counter())
    audit = []
    pop = dim.set_index("district_code")["_population"].to_dict()

    for sid, doc in state_docs.items():
        if sid.startswith("_"):
            continue
        raw_state = doc.get("state", sid.replace("_", " "))
        st = xw.norm_state(raw_state)
        for label, vals in (doc.get("districts") or {}).items():
            nums = {k: v for k, v in (vals or {}).items()
                    if isinstance(v, (int, float)) and not isinstance(v, bool)}
            if not nums:
                continue
            targets, cat, detail = xw.resolve_label(raw_state, label, names_by_state)
            lookup_state = detail if cat == xw.CROSS_STATE else st
            codes = [code_of.get((lookup_state, t)) for t in targets]
            codes = [c for c in codes if c]
            audit.append({"source_state": raw_state, "label": label,
                          "category": cat, "targets": ";".join(targets),
                          "n_codes": len(codes),
                          "values": json.dumps(nums)})
            if not codes:
                continue
            if cat == xw.PRORATE and len(codes) > 1:
                w = np.array([pop.get(c) or 0.0 for c in codes], dtype=float)
                w = (w / w.sum()) if w.sum() > 0 else np.full(len(codes), 1.0 / len(codes))
            else:
                w = np.ones(len(codes))          # split children sum into parent
            for c, wi in zip(codes, w):
                for k, v in nums.items():
                    by_code[c][k] += v * wi
    return {c: dict(v) for c, v in by_code.items()}, pd.DataFrame(audit)


def match_factsheet(factsheet, dim, names_by_state, code_of, fields):
    """nfhs5_factsheet is keyed by state__district NAME. Join it through the
    same crosswalk, keeping only the clean fields (M-10)."""
    out, audit = {}, []
    for _id, doc in factsheet.items():
        st, nm = doc.get("state_name"), doc.get("district_name_text")
        if not st or not nm:
            continue
        targets, cat, detail = xw.resolve_label(st, nm, names_by_state)
        lookup_state = detail if cat == xw.CROSS_STATE else xw.norm_state(st)
        codes = [code_of.get((lookup_state, t)) for t in targets]
        codes = [c for c in codes if c]
        audit.append({"source_state": st, "label": nm, "category": cat,
                      "targets": ";".join(targets), "n_codes": len(codes)})
        if len(codes) != 1:
            continue                     # never split a rate across districts
        vals = {f: doc.get(f) for f in fields
                if isinstance(doc.get(f), (int, float))}
        if vals:
            out.setdefault(codes[0], {}).update(vals)
    return out, pd.DataFrame(audit)


# ---------------------------------------------------------------------------
# Indicator tree
# ---------------------------------------------------------------------------
# Direction: +1 raises attractiveness, -1 lowers it.
#
# SIZE is deliberately NOT a pillar (audit C-02/C-07): treating population,
# urbanisation and age as a reflective scale gave Cronbach alpha = -0.432,
# i.e. they do not measure a common latent construct. They are formative
# drivers of market size and enter through a separate multiplicative term.
SIZE = {
    "population": +1,          # the patient pool. Rank-normalised (see below).
    "urban_share": +1,         # urban markets carry higher per-capita pharma spend
}

PILLARS = {
    # --- burden ------------------------------------------------------------
    "P2_chronic": {
        "wom_bld_sugar_high": +1, "men_bld_sugar_high": +1,
        "wom_bp_ele_med": +1, "men_bp_ele_med": +1,
        "wom_obese": +1, "wom_wh_ratio": +1,
        "tobaco_men_15": +1, "alcohol_men_15": +1,
        # R-09/M-04: an OLDER population is more chronic-attractive. v1 had
        # pop_below_15 with +1 inside 'scale', which biased the chronic index
        # toward young high-fertility districts — backwards.
        "pop_below_15": -1,
        # treatment-seeking: people who already medicate are addressable demand
        "fs_women_high_sugar_control_with_medicine": +1,
        "fs_men_high_sugar_control_with_medicine": +1,
    },
    "P2_acute": {
        "child_6_59_anemic": +1, "wom_15_49_anaemic": +1,
        "cd_ari_2wks": +1, "cd_drh_2wks": +1,
        "child_5_stunted": +1, "child_5_underweight": +1,
        "pop_hh_dw": -1, "pop_hh_sf": -1,
        "tb_per_lakh": +1,
        "pop_0_6_share": +1,          # paediatric segment (R-09)
    },
    # --- context -----------------------------------------------------------
    "P3_access": {
        "dc_insti_births": +1, "births_skill_personnel": +1,
        "cv_12_23_full_vacc": +1, "mc_anc_4": +1,
        "cv_12_23_vac_private": +1,
        "hosp_per_lakh": +1,
        # NOTE hosp_private_per_lakh is REMOVED (R-06/C-08): it is a component
        # of the proxy-demand validation target. An indicator cannot be both an
        # input and the thing that validates the input.
    },
    "P4_afford": {
        "hh_hlth_ins_fs": +1, "fem_literacy": +1,
        "pop_hh_elec": +1, "hh_fuel_cooking": +1,
        # M-11/R-02: restored by the SECC code repair. These are the only
        # genuine ability-to-pay variables in the model.
        "inc_gt10k_share": +1, "deprivation_share": -1, "vehicle_share": +1,
        # M-16: out-of-pocket spend is WALLET SIZE for a pharma market, but the
        # sign is genuinely arguable, so it is isolated in its own indicator
        # and the sensitivity analysis flips it.
        "fs_out_of_pocket_expenditure": +1,
    },
    # --- momentum, split by therapy (M-06/R-15) ----------------------------
    # NFHS deltas are differences of two survey estimates, so sampling noise
    # dominates and most pairs are near-uncorrelated. Measured over all 13
    # candidate deltas the mean |r| is 0.11. The pillars below are therefore
    # PRUNED to the groupings that actually cohere (Cronbach alpha in
    # brackets) rather than padded to look comprehensive:
    #   chronic  d_wom_obese + d_births_c_section          alpha 0.62
    #   acute    the two anaemia deltas + diarrhoea        alpha 0.63
    #   adoption d_dc_insti_births + d_pop_below_15        alpha 0.54
    # Dropped for incoherence: d_child_5_overweight, d_wom_bmi_normal,
    # d_avg_delivery_exp_phf, d_pop_hh_sf, d_child_5_stunted, d_hh_hlth_ins_fs.
    # Momentum carries only 10% of quality weight precisely because its
    # reliability is the weakest in the model — that is stated, not hidden.
    "P5_mom_chronic": {
        "d_wom_obese": +1,               # metabolic burden rising
        "d_births_c_section": +1,        # procedure//spend intensity rising
    },
    "P5_mom_acute": {
        "d_child_6_59_anemic": +1,
        "d_wom_15_49_anaemic": +1,
        "d_cd_drh_2wks": +1,
    },
    "P5_mom_adoption": {
        "d_dc_insti_births": +1,         # formal-care adoption spreading
        "d_pop_below_15": -1,            # population ageing = chronic demand up
    },
}

# Everything the momentum pillars need a delta for.
MOMENTUM_BASE = sorted({f[2:] for p in PILLARS for f in PILLARS[p]
                        if f.startswith("d_")})

# Clean factsheet fields worth adding (verified zero negatives in the audit).
FACTSHEET_FIELDS = ["women_high_sugar_control_with_medicine",
                    "men_high_sugar_control_with_medicine",
                    "out_of_pocket_expenditure"]

ALL_INDICATORS = [f for p in PILLARS.values() for f in p]


def build(min_coverage=0.80):
    """Returns (feat, dim, meta, provenance dict)."""
    ind = D.load("district_indicators")
    pca, pca_fixed = D.load_pca_repaired()
    secc = D.load_secc_repaired()
    tb = D.load("tb_live")
    pmjay = D.load("pmjay_hospitals")
    factsheet = D.load("nfhs5_factsheet")

    dim = D.build_spine(ind, pca)
    names_by_state = D.spine_names_by_state(dim)
    code_of = D.code_lookup(dim)

    problems = xw.validate_aliases(names_by_state)
    if problems:
        raise ValueError("crosswalk alias table has %d bad targets: %s"
                         % (len(problems), problems[:8]))

    dim["_population"] = dim["district_code"].map(
        lambda c: (pca.get(c) or {}).get("population_2011_total"))

    tb_by_code, tb_audit = match_named_source(tb, dim, names_by_state, code_of)
    pm_by_code, pm_audit = match_named_source(pmjay, dim, names_by_state, code_of)
    fs_by_code, fs_audit = match_factsheet(factsheet, dim, names_by_state,
                                           code_of, FACTSHEET_FIELDS)

    sentinels = detect_nfhs4_sentinels(ind)

    rows = []
    for r in dim.itertuples():
        c = r.district_code
        row = {"district_code": c, "district_name": r.district_name,
               "state_name": r.state_name}
        nf = (ind.get(c) or {}).get("nfhs", {})
        f5, f4 = nf.get(NF5) or {}, nf.get(NF4) or {}
        for f in set(ALL_INDICATORS):
            if not f.startswith(("d_", "fs_")) and f in f5:
                row[f] = f5.get(f)
        for f in MOMENTUM_BASE:
            v5, v4 = f5.get(f), f4.get(f)
            if f in sentinels and v4 == 0:
                v4 = None
            row["d_" + f] = (v5 - v4) if (v5 is not None and v4 is not None) else None

        p = pca.get(c) or {}
        pop = p.get("population_2011_total")
        row["population"] = pop
        urb = p.get("pop_urban_total")
        row["urban_share"] = (urb / pop * 100) if (urb and pop) else None
        p06 = p.get("pop_0_6_rural_total", 0) + p.get("pop_0_6_urban_total", 0)
        row["pop_0_6_share"] = (p06 / pop * 100) if (p06 and pop) else None

        sc = (secc.get(c) or {}).get("categories", {}).get("all", {})
        th = sc.get("tot_hh")
        if th:
            row["inc_gt10k_share"] = (sc.get("mon_inc_gt_10k") or 0) / th * 100
            row["deprivation_share"] = (sc.get("hh_considered_deprivation") or 0) / th * 100
            row["vehicle_share"] = (sc.get("own_motor_vehicle") or 0) / th * 100

        t = tb_by_code.get(c) or {}
        tb_tot = (t.get("public") or 0) + (t.get("private") or 0)
        if pop and tb_tot:
            row["tb_per_lakh"] = tb_tot / pop * 100000
            row["tb_private_share"] = (t.get("private") or 0) / tb_tot * 100
        m = pm_by_code.get(c) or {}
        pm_tot = (m.get("public") or 0) + (m.get("private") or 0)
        if pop and pm_tot:
            row["hosp_per_lakh"] = pm_tot / pop * 100000
            row["hosp_private_per_lakh"] = (m.get("private") or 0) / pop * 100000

        for f, v in (fs_by_code.get(c) or {}).items():
            row["fs_" + f] = v
        rows.append(row)

    feat = pd.DataFrame(rows).set_index("district_code")
    scored = feat[feat.index.isin(ind.keys())]

    prov = {
        "pca_repaired": pca_fixed,
        "nfhs4_sentinel_fields": sorted(sentinels),
        "n_sentinel_fields": len(sentinels),
        "tb_audit": tb_audit, "pm_audit": pm_audit, "fs_audit": fs_audit,
        "secc_joined": sum(1 for c in scored.index if c in secc),
        "n_spine": len(dim), "n_scored": len(scored),
    }
    return feat, scored, dim, prov
