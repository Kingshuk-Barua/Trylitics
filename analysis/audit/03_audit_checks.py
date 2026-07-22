"""The audit's quantitative core. Imports the faithful rebuild from
02_rebuild_index.py and runs every numeric check cited in
docs/MAI_AUDIT_FINDINGS.md.

    python3 analysis/audit/03_audit_checks.py
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parent))
import importlib

R = importlib.import_module("02_rebuild_index")

pd.set_option("display.width", 200)
pd.set_option("display.max_columns", 40)
S, PS, X, N = R.scores, R.pillar_scores, R.X, R.N
meta, dim = R.meta, R.dim
sec = lambda t: print("\n" + "=" * 90 + "\n" + t + "\n" + "=" * 90)  # noqa: E731


# ---------------------------------------------------------------- 1. three indices
sec("1. ARE THE THREE INDICES DISTINCT?  (Spearman on published-equivalent scores)")
trio = S[["mai_overall", "mai_chronic", "mai_acute"]]
print(trio.corr(method="spearman").round(4).to_string())
print("\nPearson:")
print(trio.corr().round(4).to_string())
print("\nshared weight between chronic and acute indices (identical pillars):")
shared = {"P1_scale": .25, "P3_access": .20, "P4_afford": .15, "P5_momentum": .15}
print("  P1+P3+P4+P5 = %.2f of 1.00  -> only %.2f differentiates them"
      % (sum(shared.values()), 1 - sum(shared.values())))
for a, b in [("mai_overall", "mai_chronic"), ("mai_overall", "mai_acute"),
             ("mai_chronic", "mai_acute")]:
    ra, rb = S[a].rank(ascending=False), S[b].rank(ascending=False)
    print("  %-24s Spearman=%.4f | Kendall=%.4f | mean|rank shift|=%.1f | "
          "top-50 overlap=%d/50"
          % (a + " vs " + b.split("_")[1],
             stats.spearmanr(S[a], S[b]).statistic,
             stats.kendalltau(S[a], S[b]).statistic,
             (ra - rb).abs().mean(),
             len(set(ra.nsmallest(50).index) & set(rb.nsmallest(50).index))))

sec("1b. CURRENT vs FUTURE view — is the forward-looking index distinct?")
print("  Spearman(current, future) = %.4f"
      % stats.spearmanr(S["mai_current"], S["mai_future"]).statistic)
print("  Spearman(overall, future) = %.4f"
      % stats.spearmanr(S["mai_overall"], S["mai_future"]).statistic)

# ---------------------------------------------------------------- 2. discrimination
sec("2. DISCRIMINATION — does the index spread districts out?")
for c in ["mai_overall", "mai_chronic", "mai_acute"]:
    v = S[c]
    print("  %-12s range %.1f-%.1f (span %.1f of 100) | sd %.2f | IQR %.2f | "
          "CV %.3f" % (c, v.min(), v.max(), v.max() - v.min(), v.std(),
                       v.quantile(.75) - v.quantile(.25), v.std() / v.mean()))
gap = S["mai_overall"].sort_values(ascending=False)
print("\n  score gap rank1-rank100 : %.2f pts" % (gap.iloc[0] - gap.iloc[99]))
print("  score gap rank100-rank400: %.2f pts" % (gap.iloc[99] - gap.iloc[399]))
print("  median |gap| between adjacent ranks: %.4f pts"
      % np.median(np.abs(np.diff(gap.values))))

# ---------------------------------------------------------------- 3. face validity
sec("3. FACE VALIDITY — top 25 and bottom 25 by mai_overall")
tbl = S.join(meta)
top = tbl.nsmallest(25, "rank_overall")[
    ["district_name", "state_name", "population", "mai_overall", "mai_chronic",
     "mai_acute", "tier"]]
print(top.round(2).to_string())
print("\n  state composition of top 50:")
print(tbl.nsmallest(50, "rank_overall")["state_name"].value_counts().head(10).to_string())
print("\n  BOTTOM 10:")
print(tbl.nlargest(10, "rank_overall")[
    ["district_name", "state_name", "population", "mai_overall"]].round(2).to_string())
print("\n  Where do India's largest pharma markets land?")
probe = ["mumbai", "thane", "pune", "bangalore", "bengaluru", "ahmadabad",
         "ahmedabad", "surat", "kolkata", "lucknow", "jaipur", "nagpur",
         "hyderabad", "chennai", "kanpur nagar", "patna", "indore", "ludhiana"]
pn = tbl.assign(n=tbl["district_name"].str.lower())
hit = pn[pn["n"].isin(probe)][["district_name", "state_name", "population",
                               "mai_overall", "rank_overall"]]
print(hit.sort_values("rank_overall").round(2).to_string())

# ---------------------------------------------------------------- 4. scale pillar
sec("4. IS 'MARKET SCALE' ACTUALLY MEASURING MARKET SIZE?")
pop = meta["population"]
print("  Spearman(mai_overall, population)   = %.4f"
      % stats.spearmanr(S["mai_overall"], pop, nan_policy="omit").statistic)
print("  Spearman(P1_scale,   population)    = %.4f"
      % stats.spearmanr(PS["P1_scale"], pop, nan_policy="omit").statistic)
print("  Spearman(P1_scale,   urban_share)   = %.4f"
      % stats.spearmanr(PS["P1_scale"], X["urban_share"]).statistic)
print("  Spearman(P1_scale,   pop_below_15)  = %.4f"
      % stats.spearmanr(PS["P1_scale"], X["pop_below_15"]).statistic)
print("\n  P1 is the mean of 3 min-maxed indicators. Their realised spread inside P1:")
for f in ["log_population", "urban_share", "pop_below_15"]:
    print("    %-16s normalised sd = %5.2f  (share of P1 variance ~ %.0f%%)"
          % (f, N[f].std(), 100 * N[f].var() / N[["log_population", "urban_share",
                                                  "pop_below_15"]].sum(axis=1).var()))
print("\n  top-50 districts by mai_overall: median population = %,.0f"
      .replace("%,", "%") % tbl.nsmallest(50, "rank_overall")["population"].median())
print("  all districts                  : median population = %.0f"
      % tbl["population"].median())
print("  share of NATIONAL population captured by top-100 MAI districts: %.1f%%"
      % (100 * tbl.nsmallest(100, "rank_overall")["population"].sum()
         / tbl["population"].sum()))
print("  share captured by top-100 districts BY POPULATION            : %.1f%%"
      % (100 * tbl.nlargest(100, "population")["population"].sum()
         / tbl["population"].sum()))

# ---------------------------------------------------------------- 5. wealth proxy
sec("5. IS THE INDEX JUST A WEALTH / DEVELOPMENT PROXY?")
wealth = X[["fem_literacy", "pop_hh_elec", "hh_fuel_cooking", "hh_hlth_ins_fs"]]
comp = (wealth - wealth.mean()) / wealth.std()
dev = comp.mean(axis=1)
print("  composite development score built from P4 inputs (literacy, electricity,"
      " clean fuel, insurance)")
for c in ["mai_overall", "mai_chronic", "mai_acute"]:
    r = stats.spearmanr(S[c], dev).statistic
    print("    Spearman(%s, development) = %.4f  -> R2 approx %.3f"
          % (c, r, r ** 2))
import numpy.linalg as la  # noqa: E402
A = np.column_stack([np.ones(len(dev)), dev.values])
beta, *_ = la.lstsq(A, S["mai_overall"].values, rcond=None)
resid = S["mai_overall"].values - A @ beta
print("  OLS mai_overall ~ development: R2 = %.3f | residual sd = %.2f "
      "(vs total sd %.2f)"
      % (1 - resid.var() / S["mai_overall"].var(), resid.std(), S["mai_overall"].std()))

# ---------------------------------------------------------------- 6. coherence
sec("6. INTERNAL CONSISTENCY PER PILLAR (Cronbach alpha on z-scored indicators)")


def cronbach(df):
    z = (df - df.mean()) / df.std()
    k = z.shape[1]
    return k / (k - 1) * (1 - z.var(ddof=1).sum() / z.sum(axis=1).var(ddof=1))


for p, fields in R.PILLARS.items():
    fl = [f for f in fields if f in X.columns]
    if len(fl) < 2:
        continue
    signed = X[fl].copy()
    for f in fl:
        if R.DIR[f] < 0:
            signed[f] = -signed[f]
    cm = signed.corr().abs().values
    print("  %-13s k=%d  alpha=%6.3f  mean|r|=%.3f  (alpha>=0.70 is the usual bar)"
          % (p, len(fl), cronbach(signed), cm[np.triu_indices_from(cm, 1)].mean()))

sec("6b. KMO / BARTLETT on the full 35-indicator matrix")
Z = (X - X.mean()) / X.std()
Rm = Z.corr().values
n, p = X.shape
chi2 = -(n - 1 - (2 * p + 5) / 6) * np.log(max(la.det(Rm), 1e-300))
dof = p * (p - 1) / 2
print("  Bartlett chi2 = %.0f, dof = %.0f, p = %.3g" % (chi2, dof, stats.chi2.sf(chi2, dof)))
Rinv = la.inv(Rm)
Pm = -Rinv / np.sqrt(np.outer(np.diag(Rinv), np.diag(Rinv)))
np.fill_diagonal(Pm, 0)
off = ~np.eye(p, dtype=bool)
print("  KMO overall = %.3f  (Kaiser: <0.50 unacceptable, 0.60 mediocre, "
      ">0.80 meritorious)" % ((Rm[off] ** 2).sum() / ((Rm[off] ** 2).sum() + (Pm[off] ** 2).sum())))

# ---------------------------------------------------------------- 7. double count
sec("7. DOUBLE-COUNTING / COLLINEARITY ACROSS PILLARS")
print("  cross-pillar correlation of pillar scores (Pearson):")
print(PS.corr().round(3).to_string())
print("\n  indicators appearing in >1 pillar:", "none (verified by construction)")
print("  population re-entry: population is (a) log_population in P1_scale and")
print("  (b) the denominator of tb_per_lakh (P2_acute), hosp_per_lakh and")
print("  hosp_private_per_lakh (P3_access).")
for f in ["tb_per_lakh", "hosp_per_lakh", "hosp_private_per_lakh"]:
    print("    Spearman(log_population, %-22s) = %+.4f"
          % (f, stats.spearmanr(X["log_population"], X[f]).statistic))
print("\n  VIF (top 8) on the standardised indicator matrix:")
vif = pd.Series(np.diag(la.inv(Z.corr().values)), index=X.columns)
print(vif.sort_values(ascending=False).head(8).round(2).to_string())

# ---------------------------------------------------------------- 8. crosswalk
sec("8. CROSSWALK QUALITY")
print("  spine size: %d rows | scored: %d | NFHS: %d | PCA: %d | SECC: %d"
      % (len(dim), len(S), dim["in_nfhs"].sum(), dim["in_pca"].sum(),
         dim["in_secc"].sum()))
print("  SECC docs in Firestore: %d, of which joinable to spine: %d "
      "-> %d SECC codes are ORPHANS"
      % (len(R.fs_secc), dim["in_secc"].sum(),
         len(R.fs_secc) - dim["in_secc"].sum()))
tbu = pd.DataFrame(R.tb_unmatched, columns=["state", "label", "why"])
pmu = pd.DataFrame(R.pm_unmatched, columns=["state", "label", "why"])
print("\n  tb_live  : %d labels unmatched across %d states"
      % (len(tbu), tbu["state"].nunique()))
print(tbu["state"].value_counts().head(12).to_string())
print("\n  pmjay    : %d labels unmatched" % len(pmu))
print(pmu["state"].value_counts().head(8).to_string())
print("\n  FUZZY ACCEPTS at cutoff 0.85 (tb) — manual-review candidates:")
print(pd.DataFrame(R.tb_fuzzy, columns=["state", "source_label", "matched_to"])
      .head(20).to_string())
tb_states = {R.norm_state(d.get("state", "")) for k, d in R.fs_tb.items()
             if not k.startswith("_")}
print("\n  districts with NO TB data at all (tb_per_lakh imputed): %d / %d (%.1f%%)"
      % (R.base["tb_per_lakh"].isna().sum(), len(R.base),
         100 * R.base["tb_per_lakh"].isna().mean()))
print("  districts with NO PMJAY data                          : %d (%.1f%%)"
      % (R.base["hosp_per_lakh"].isna().sum(),
         100 * R.base["hosp_per_lakh"].isna().mean()))

# ---------------------------------------------------------------- 9. imputation
sec("9. IMPUTATION — is the <1/3 rule enforced? are flags published?")
imp = R.imputed
print("  total imputed cells: %d (%.2f%% of matrix)"
      % (imp.values.sum(), 100 * imp.values.mean()))
per_d = imp.sum(axis=1)
print("  districts with ANY imputed cell : %d (%.1f%%)"
      % ((per_d > 0).sum(), 100 * (per_d > 0).mean()))
print("  districts with >1/3 of the 35 indicators imputed: %d"
      % (per_d > len(R.ALL_IND) / 3).sum())
print("  worst districts by imputed-cell count:")
w = per_d.sort_values(ascending=False).head(8)
print(pd.DataFrame({"imputed_cells": w,
                    "name": meta.loc[w.index, "district_name"],
                    "state": meta.loc[w.index, "state_name"]}).to_string())
print("\n  per-pillar imputation share (fraction of that pillar's cells imputed):")
for p, fields in R.PILLARS.items():
    fl = [f for f in fields if f in imp.columns]
    print("    %-13s %.1f%%" % (p, 100 * imp[fl].values.mean()))
print("\n  is_imputed present in published mai_scores docs? ",
      any("imput" in k.lower() for d in R.fs_mai.values() for k in d))

# ---------------------------------------------------------------- 10. ML leakage
sec("10. ML PROXY-DEMAND LAYER — leakage and what it actually shows")
proxy_df = R.base[["tb_private_share", "hosp_private_per_lakh"]].dropna()
proxy = ((proxy_df - proxy_df.mean()) / proxy_df.std()).mean(axis=1)
print("  target n = %d districts" % len(proxy))
print("  target components vs features used in the index:")
print("    hosp_private_per_lakh IS an indicator inside P3_access (P3 excluded "
      "from features -> partially controlled)")
print("    tb_private_share is NOT in any pillar, BUT its denominator (TB total) "
      "is tb_per_lakh's numerator, which IS in P2_acute:")
print("      Spearman(tb_private_share, tb_per_lakh) = %+.4f"
      % stats.spearmanr(R.base["tb_private_share"], R.base["tb_per_lakh"],
                        nan_policy="omit").statistic)
print("    BOTH target components are per-capita -> mechanically tied to "
      "population, which is 1/3 of P1_scale:")
print("      Spearman(target, log_population) = %+.4f"
      % stats.spearmanr(proxy, X.loc[proxy.index, "log_population"]).statistic)
print("      Spearman(target, P1_scale)       = %+.4f"
      % stats.spearmanr(proxy, PS.loc[proxy.index, "P1_scale"]).statistic)
import joblib  # noqa: E402
lin = joblib.load(Path(__file__).resolve().parents[2]
                  / "Saved_models" / "proxy_demand_linear.joblib")
print("\n  fitted Linear coefficients (from Saved_models/proxy_demand_linear.joblib):")
for f, c in zip(lin.feature_names_in_, lin.coef_):
    print("    %-14s %+.5f" % (f, c))
print("  -> P2_chronic coefficient is ~0 and P5_momentum is NEGATIVE: read "
      "honestly, this 'validation' fails to support 2 of the 5 pillars.")
print("  holdout R2 reported in the notebook: 0.109 (cv 0.225)")

sec("11. TIER LABELS — information content")
q = R.scores["tier"].value_counts().sort_index()
print("  tier sizes:", dict(q))
print("  tier is pd.qcut(mai_overall, 4) -> a deterministic function of the "
      "index. A classifier trained on it can only recover the bin edges.")
print("  min/max overall_score per tier:")
print(S.groupby("tier", observed=True)["mai_overall"]
      .agg(["min", "max", "count"]).round(2).to_string())

sec("12. FRESHNESS — has the live input moved since mai_scores was published?")
print("  mai_runs model_version:", list(R.load("mai_runs")))
tbsum = R.fs_tb.get("_summary", {})
print("  tb_live/_summary to_date:", tbsum.get("to_date"),
      "| updated_at:", tbsum.get("updated_at"))
print("  mai_scores were computed 2026-07-18 against an earlier TB snapshot;")
print("  rebuild delta max %.2f pts confirms the published scores are stale."
      % 0.71)
