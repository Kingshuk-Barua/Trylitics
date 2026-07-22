"""Imputation with the coverage rules the plan specified and v1 never enforced.

Audit C-06: `MAI_MODEL_PLAN.md` section 3.2 requires "keep an indicator only if
>=80% of districts have valid values; impute only when <1/3 missing", and
section 3.3 requires "every imputation logged". v1 computed an `imputed` mask,
plotted it once, and published nothing — `is_imputed` was absent from all 698
`mai_scores` documents.

This module enforces both rules and returns per-cell provenance so the flags
can reach Firestore.

Order of operations (fixes M-19): coverage gate -> imputation. There is no
winsorisation step at all under rank normalisation, so the impute/winsorise
ordering bug is structurally gone rather than merely reordered.
"""
import numpy as np
import pandas as pd

STATE_MEDIAN, NATIONAL_MEDIAN, OBSERVED = "state_median", "national_median", "observed"


def coverage_gate(X, indicators, min_coverage=0.80):
    """Drop indicators below the JRC coverage floor. Returns (kept, report)."""
    cov = X[indicators].notna().mean()
    kept = [f for f in indicators if cov[f] >= min_coverage]
    report = pd.DataFrame({"coverage": cov,
                           "kept": cov >= min_coverage}).sort_values("coverage")
    return kept, report


def impute(X, states, pillars, max_pillar_missing=1.0 / 3.0):
    """Within-state median, then national median, with provenance.

    The <1/3 rule is applied PER PILLAR PER DISTRICT, which is what the plan
    means: a district missing more than a third of a pillar's indicators has
    that pillar set to NaN rather than fabricated from medians. Its weight is
    then re-allocated across the pillars it does have — the NITI Aayog State
    Health Index convention (verified in the audit, M-20), which is more
    defensible than inventing values.
    """
    prov = pd.DataFrame(OBSERVED, index=X.index, columns=X.columns)
    prov[X.isna()] = np.nan

    out = X.copy()
    state_med = out.groupby(states).transform("median")
    fill_state = out.isna() & state_med.notna()
    out = out.fillna(state_med)
    prov[fill_state] = STATE_MEDIAN

    nat_med = out.median()
    fill_nat = out.isna()
    out = out.fillna(nat_med)
    prov[fill_nat] = NATIONAL_MEDIAN

    # per-district, per-pillar missingness measured BEFORE imputation
    was_missing = X.isna()
    pillar_missing = {}
    pillar_blocked = {}
    for p, fields in pillars.items():
        fl = [f for f in fields if f in X.columns]
        if not fl:
            continue
        share = was_missing[fl].mean(axis=1)
        pillar_missing[p] = share
        pillar_blocked[p] = share > max_pillar_missing
    return (out, prov, pd.DataFrame(pillar_missing),
            pd.DataFrame(pillar_blocked))


def impute_strategy(X, states, pillars, strategy, k=5,
                    max_pillar_missing=1.0 / 3.0):
    """Alternative fill rules, for the Layer 4.2 sensitivity arm.

    `state_median` is the production path and simply delegates to `impute()`,
    so the sensitivity test compares the real pipeline against the
    alternatives rather than against a re-implementation of itself.

      national_median  ignore the state hierarchy entirely
      knn              k-nearest neighbours (k=5) on z-scored indicators —
                       the only strategy that uses cross-indicator structure
      listwise         no imputation at all; districts with ANY missing kept
                       indicator are dropped. This is the strategy that
                       changes n, which is exactly why it is included: if the
                       ranking only survives because 690-odd districts were
                       partially invented, listwise will say so.

    Returns (filled, provenance, pillar_blocked). Pillar blocking is computed
    from pre-imputation missingness in every arm, so the <1/3 rule is applied
    identically and the comparison isolates the fill rule alone.
    """
    if strategy == "state_median":
        out, prov, _, blocked = impute(X, states, pillars, max_pillar_missing)
        return out, prov, blocked

    was_missing = X.isna()
    blocked = pd.DataFrame(
        {p: was_missing[[f for f in fl if f in X.columns]].mean(axis=1)
            > max_pillar_missing
         for p, fl in pillars.items()
         if [f for f in fl if f in X.columns]})

    if strategy == "national_median":
        out = X.fillna(X.median())
    elif strategy == "knn":
        from sklearn.impute import KNNImputer
        mu, sd = X.mean(), X.std().replace(0, np.nan)
        Z = (X - mu) / sd
        Zi = pd.DataFrame(KNNImputer(n_neighbors=k).fit_transform(Z),
                          index=X.index, columns=X.columns)
        out = Zi * sd + mu
        # KNNImputer drops all-NaN columns silently; restore via national median
        out = out.fillna(X.median())
    elif strategy == "listwise":
        keep = X.notna().all(axis=1)
        out = X[keep].copy()
        blocked = blocked.loc[out.index]
    else:
        raise ValueError("unknown strategy %r" % strategy)

    prov = pd.DataFrame(OBSERVED, index=out.index, columns=out.columns)
    prov[X.reindex(out.index).isna()] = strategy
    return out, prov, blocked


def imputation_summary(prov, pillars):
    total = prov.size
    counts = {
        "observed": int((prov == OBSERVED).values.sum()),
        "state_median": int((prov == STATE_MEDIAN).values.sum()),
        "national_median": int((prov == NATIONAL_MEDIAN).values.sum()),
    }
    counts["imputed_pct"] = round(
        100.0 * (counts["state_median"] + counts["national_median"]) / total, 3)
    per_pillar = {}
    for p, fields in pillars.items():
        fl = [f for f in fields if f in prov.columns]
        if fl:
            per_pillar[p] = round(
                100.0 * float((prov[fl] != OBSERVED).values.mean()), 2)
    counts["per_pillar_imputed_pct"] = per_pillar
    return counts


def per_district_flags(prov, pillars):
    """{district_code: {pillar: imputed_share}} for publishing (R-05)."""
    out = {}
    for p, fields in pillars.items():
        fl = [f for f in fields if f in prov.columns]
        if not fl:
            continue
        share = (prov[fl] != OBSERVED).mean(axis=1)
        for code, v in share.items():
            out.setdefault(code, {})[p] = round(float(v), 3)
    return out
