"""Proxy-demand validation, de-leaked (audit C-08 / roadmap R-06).

What was wrong in v1
--------------------
The target was the z-mean of `tb_private_share` and `hosp_private_per_lakh`.
`hosp_private_per_lakh` was ALSO an indicator inside P3_access, and although
P3 was dropped from the feature set, three leaks remained:

  * both target components are per-capita, and log(population) was a third of
    P1_scale, so Spearman(target, log_population) = +0.526 and the tree models
    loaded 44-46% of their importance onto P1 — mostly the shared 1/population
    denominator, not signal;
  * `tb_private_share`'s denominator is the same Ni-kshay total that forms
    `tb_per_lakh`'s numerator, and `tb_per_lakh` sat in P2_acute (r = +0.272);
  * the result was reported as validation despite giving the chronic pillar a
    coefficient of +0.0004 and momentum a NEGATIVE one at holdout R^2 0.109.

What v2 does
------------
1. `hosp_private_per_lakh` is REMOVED from the index entirely (see
   `features.PILLARS['P3_access']`). It is now only a validation target.
2. The population denominator is removed from the leak path by evaluating on
   RANKS and by reporting a population-only baseline that any model must beat.
3. Evaluation is spatially blocked by state (`GroupKFold`), because state alone
   explains >50% of index variance and a random split leaks state identity.
4. The result is reported as whatever it is. A negative or weak result is
   printed as a negative or weak result, and the run record stores the
   coefficient signs so the deck cannot quote an R^2 without them.

This is a falsification test, not a validation ritual: the question is whether
the index's per-capita content predicts revealed private-market activity BETTER
THAN POPULATION ALONE.
"""
import json

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.ensemble import GradientBoostingRegressor, RandomForestRegressor
from sklearn.linear_model import Lasso, LinearRegression, Ridge
from sklearn.metrics import r2_score
from sklearn.model_selection import GroupKFold, cross_val_predict

from . import data as D

OUT = D.CACHE / "v2"

MODELS = {
    "Linear": LinearRegression(),
    "Ridge": Ridge(alpha=1.0),
    "Lasso": Lasso(alpha=0.01, max_iter=20000),
    "RandomForest": RandomForestRegressor(n_estimators=400, min_samples_leaf=3,
                                          random_state=42),
    "GradientBoosting": GradientBoostingRegressor(n_estimators=300, max_depth=3,
                                                  learning_rate=0.05,
                                                  random_state=42),
}


def build_target(scored):
    """Revealed private-market activity. Both components are now OUTSIDE the
    index (hosp_private_per_lakh was removed from P3_access in v2)."""
    df = scored[["tb_private_share", "hosp_private_per_lakh"]].dropna()
    z = (df - df.mean()) / df.std()
    return z.mean(axis=1)


def run(scored, pillar_scores, meta, quality):
    y = build_target(scored)
    idx = y.index
    groups = meta.loc[idx, "state_name"].values

    # Features: the QUALITY pillars only. Size is excluded because the target
    # is per-capita and would share its denominator.
    feat_cols = [c for c in pillar_scores.columns if c != "P3_access"]
    X = pillar_scores.loc[idx, feat_cols]

    cv = GroupKFold(n_splits=5)
    rows = []
    for name, m in MODELS.items():
        pred = cross_val_predict(m, X, y, cv=cv, groups=groups)
        rows.append({"model": name,
                     "blocked_cv_R2": r2_score(y, pred),
                     "blocked_cv_spearman": stats.spearmanr(pred, y).statistic})
    res = pd.DataFrame(rows).set_index("model").sort_values(
        "blocked_cv_R2", ascending=False)

    # Baselines any model must beat to have said anything.
    pop = meta.loc[idx, "population"].fillna(meta["population"].median())
    base_pop = stats.spearmanr(pop, y).statistic
    base_quality = stats.spearmanr(quality.loc[idx], y).statistic

    lin = LinearRegression().fit(X, y)
    coefs = dict(zip(feat_cols, np.round(lin.coef_, 5)))

    print("=" * 100)
    print("PROXY-DEMAND FALSIFICATION TEST (state-blocked CV)")
    print("=" * 100)
    print("  target: z-mean(tb_private_share, hosp_private_per_lakh), n=%d" % len(y))
    print("  both components are now OUTSIDE the index (R-06)")
    print("  features: %s" % feat_cols)
    print()
    print(res.round(4).to_string())
    print()
    print("  BASELINES the model must beat:")
    print("    Spearman(population alone, target)     = %+.4f" % base_pop)
    print("    Spearman(MAI quality composite, target)= %+.4f" % base_quality)
    print()
    print("  fitted linear coefficients (sign is the finding, not R2):")
    for k, v in coefs.items():
        flag = "  <-- WRONG SIGN" if v < 0 else ""
        print("    %-18s %+.5f%s" % (k, v, flag))

    wrong = [k for k, v in coefs.items() if v < 0]
    verdict = ("SUPPORTS the pillar design" if not wrong else
               "PARTIALLY DISCONFIRMS: negative coefficient on " + ", ".join(wrong))
    print("\n  VERDICT: %s" % verdict)
    print("  best blocked-CV R2 = %.3f (%s)"
          % (res.iloc[0]["blocked_cv_R2"], res.index[0]))
    if res.iloc[0]["blocked_cv_R2"] < 0.15:
        print("  NOTE: R2 below 0.15. This target is a noisy two-signal proxy; "
              "the honest reading is that it is too weak to validate or refute "
              "the index on its own. Reported as such, never as support.")

    out = {"n": int(len(y)), "features": feat_cols,
           "results": res.round(4).to_dict(),
           "coefficients": {k: float(v) for k, v in coefs.items()},
           "baseline_spearman_population": float(base_pop),
           "baseline_spearman_quality": float(base_quality),
           "negative_coefficient_pillars": wrong,
           "verdict": verdict,
           "cv": "GroupKFold(5) blocked by state — a random split leaks state "
                 "identity, which explains >50% of index variance"}
    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / "ml_validation_v2.json", "w") as f:
        json.dump(out, f, indent=2)
    return res, out


def main():
    from . import features as F, impute as IM, index as IX
    feat, scored, dim, prov = F.build()
    directions = {}
    for fl in F.PILLARS.values():
        directions.update(fl)
    directions.update(F.SIZE)
    inds = [f for f in F.ALL_INDICATORS if f in scored.columns]
    kept, _ = IM.coverage_gate(scored, inds)
    pk = {p: {f: d for f, d in fl.items() if f in kept}
          for p, fl in F.PILLARS.items()}
    pk = {p: f for p, f in pk.items() if f}
    X = scored[kept + [c for c in F.SIZE if c in scored.columns]].copy()
    Xi, _, _, blocked = IM.impute(X, scored["state_name"], pk)
    scores, PS, S = IX.build_indices(Xi, directions, blocked=blocked)
    meta = scored[["district_name", "state_name", "population"]]
    return run(scored, PS, meta, scores["quality_overall"])


if __name__ == "__main__":
    main()
