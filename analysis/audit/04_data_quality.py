"""Source-data quality probes: census_pca population integrity, the excluded
nfhs5_factsheet, SECC code vintage, TB/PMJAY coverage, and the robustness
claims. Run after 02/03.

    python3 analysis/audit/04_data_quality.py
"""
import importlib
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parent))
R = importlib.import_module("02_rebuild_index")
pd.set_option("display.width", 200)
pd.set_option("display.max_columns", 30)
sec = lambda t: print("\n" + "=" * 90 + "\n" + t + "\n" + "=" * 90)  # noqa: E731

pca, ind, secc, mai = R.fs_pca, R.fs_ind, R.fs_secc, R.fs_mai

# ------------------------------------------------------------------ population
sec("A. census_pca POPULATION INTEGRITY")
pop = pd.Series({k: v.get("population_2011_total") for k, v in pca.items()})
print("  docs: %d | population_2011_total present: %d | sum = %,.0f"
      .replace("%,", "%") % (len(pca), pop.notna().sum(), pop.sum()))
print("  Census 2011 India total was 1,210,854,977 -> pipeline sum is %.1f%% of it"
      % (100 * pop.sum() / 1210854977))
names = pd.Series({k: v.get("district_name") for k, v in pca.items()})
states = pd.Series({k: v.get("state_name") for k, v in pca.items()})
prof = pd.DataFrame({"name": names, "state": states, "pop": pop})

print("\n  Districts whose PCA population is IMPLAUSIBLY SMALL for a known metro:")
watch = ["mumbai", "hyderabad", "kolkata", "bangalore", "bengaluru", "chennai",
         "medchal malkajgiri", "gurgaon", "gautam buddha nagar", "pune",
         "ahmadabad", "surat"]
w = prof[prof["name"].str.lower().isin(watch)]
print(w.sort_values("pop").to_string())

print("\n  Districts in the SCORED set with NO population at all "
      "(log_population imputed to a state median):")
miss = R.base[R.base["population"].isna()][["district_name", "state_name"]]
miss["mai_rank"] = R.scores.loc[miss.index, "rank_overall"]
miss["mai_overall"] = R.scores.loc[miss.index, "mai_overall"].round(2)
print(miss.sort_values("mai_rank").to_string())
print("  count = %d districts scored on an imputed population" % len(miss))

print("\n  Is any district's population double-counted (a rural_urban='Total' row)?")
keys = set()
for v in pca.values():
    keys |= {k for k in v if k.startswith("pop_") and k.endswith("_total")}
print("   pop_*_total keys present across the collection:", sorted(keys))

print("\n  Reconstruction check: population_2011_total vs rural+urban components")
recon = pd.Series({k: (v.get("pop_rural_total") or 0) + (v.get("pop_urban_total") or 0)
                   for k, v in pca.items()})
print("   max |stored - (rural+urban)| = %.0f  -> %s"
      % ((pop - recon).abs().max(),
         "consistent" if (pop - recon).abs().max() < 1 else "INCONSISTENT"))
print("   docs missing pop_urban_total entirely: %d (their urban_share becomes None)"
      % sum(1 for v in pca.values() if v.get("pop_urban_total") is None))

# ------------------------------------------------------------- urban_share
sec("B. urban_share — the single most rank-influential indicator")
us = R.base["urban_share"]
print("  present %d / %d | min %.1f | median %.1f | max %.1f | ==100.0: %d districts"
      % (us.notna().sum(), len(us), us.min(), us.median(), us.max(), (us >= 99.99).sum()))
print("  districts at urban_share == 100 (they max out P1's largest component):")
u100 = R.base[us >= 99.99][["district_name", "state_name", "population"]]
u100["mai_rank"] = R.scores.loc[u100.index, "rank_overall"]
print(u100.sort_values("mai_rank").head(20).to_string())
print("  ...of which in the MAI top 50: %d"
      % (u100["mai_rank"] <= 50).sum())

# --------------------------------------------------- nfhs5_factsheet corruption
sec("C. nfhs5_factsheet (707 docs, EXCLUDED from the model) — is it usable?")
fs = R.load("nfhs5_factsheet")
fdf = pd.DataFrame(fs).T
numc = fdf.select_dtypes(include=[np.number])
neg = {}
for c in numc.columns:
    v = numc[c].dropna()
    if len(v) and (v < 0).any():
        neg[c] = (100 * (v < 0).mean(), v.min())
print("  numeric fields: %d | fields containing NEGATIVE values: %d"
      % (numc.shape[1], len(neg)))
print("  A percentage field cannot be negative. Worst offenders:")
for c, (pct, mn) in sorted(neg.items(), key=lambda x: -x[1][0])[:15]:
    print("    %-42s %5.1f%% of districts negative, min = %.1f" % (c, pct, mn))
print("\n  -> This collection carries an unflagged sentinel/parse defect. The "
      "notebook excludes it for a DIFFERENT stated reason (names-only join).")
print("  Fields it uniquely offers that the model currently lacks:")
for c in ["out_of_pocket_expenditure", "women_cervical_cancer", "women_breast_cancer",
          "women_oral_cancer", "sex_ratio", "women_very_high_sugar",
          "men_very_high_sugar", "women_high_sugar_control_with_medicine"]:
    if c in numc:
        v = numc[c].dropna()
        print("    %-42s n=%d  median=%.1f  negatives=%d"
              % (c, len(v), v.median(), int((v < 0).sum())))

# ------------------------------------------------------------------ SECC
sec("D. SECC — code vintage and the orphan join")
sc = set(secc)
sp = set(R.dim["district_code"])
print("  secc codes: %d | spine codes: %d | intersection: %d | secc-only: %d "
      "| spine-only: %d" % (len(sc), len(sp), len(sc & sp), len(sc - sp), len(sp - sc)))
ex = list(sc - sp)[:10]
print("  example SECC-only codes:", ex)
print("  their names:", [secc[c].get("district_name") for c in ex])
cats = {}
for v in secc.values():
    for k in (v.get("categories") or {}):
        cats[k] = cats.get(k, 0) + 1
print("  SECC category keys and doc counts:", cats)
alln = sum(1 for v in secc.values() if (v.get("categories") or {}).get("all"))
print("  docs with an 'all' category (the only one the notebook reads): %d" % alln)

# ------------------------------------------------------- TB / PMJAY coverage
sec("E. TB & PMJAY — what the unmatched labels actually are")
tbu = pd.DataFrame(R.tb_unmatched, columns=["state", "label", "why"])
newdist = ["nandyal", "eluru", "kakinada", "ntr", "anakapalli", "tirupati",
           "sri sathya sai", "annamayya", "bapatla", "palnadu", "konaseema",
           "parvathipuram manyam", "alluri sitharama raju", "kakinada"]
print("  Andhra Pradesh unmatched labels (the 2022 reorganisation, 13 -> 26 districts):")
print("   ", sorted(tbu[tbu["state"].str.contains("Andhra", na=False)]["label"].tolist()))
print("\n  Maharashtra unmatched (37) — sample:")
print("   ", sorted(tbu[tbu["state"] == "Maharashtra"]["label"].tolist())[:20])
print("\n  Delhi unmatched (25) — sample:")
print("   ", sorted(tbu[tbu["state"] == "Delhi"]["label"].tolist())[:15])
tot_tb_rows = sum(d.get("district_count", 0) for k, d in R.fs_tb.items()
                  if not k.startswith("_"))
print("\n  Ni-kshay district rows fetched: %d | matched into spine: %d "
      "-> %.1f%% of live TB rows are DISCARDED"
      % (tot_tb_rows, len(R.tb_by_code), 100 * (1 - len(R.tb_by_code) / tot_tb_rows)))
tb_notif = sum(v.get("total", 0) for d in R.fs_tb.values() if isinstance(d, dict)
               for v in (d.get("districts") or {}).values() if isinstance(v, dict))
matched_notif = sum((v.get("public") or 0) + (v.get("private") or 0)
                    for v in R.tb_by_code.values())
print("  TB notifications total in tb_live: %d | carried into the index: %d "
      "(%.1f%%)" % (tb_notif, matched_notif, 100 * matched_notif / tb_notif))

# ------------------------------------------------------------ robustness redo
sec("F. RE-RUNNING THE ROBUSTNESS CLAIM (top-50 stability = 95.2%)")
PS = R.pillar_scores
RNG = np.random.RandomState(42)
n_mc = 500
ranks_mc = np.zeros((n_mc, len(PS)))
for i in range(n_mc):
    w = {k: R.W_BUSINESS[k] * RNG.uniform(.75, 1.25) for k in R.W_BUSINESS}
    ranks_mc[i] = R.agg(PS, w).rank(ascending=False).values
top50 = set(R.scores.nsmallest(50, "rank_overall").index)
stab = np.mean([len(top50 & set(PS.index[np.argsort(ranks_mc[i])][:50])) / 50
                for i in range(n_mc)])
print("  reproduced top-50 stability under +/-25%% weight perturbation: %.1f%%"
      % (100 * stab))
print("  BUT the perturbation only varies WEIGHTS. The plan (and JRC) also "
      "require normalisation and aggregation swaps. Their effect:")
zc = (R.Xw - R.Xw.mean()) / R.Xw.std()
Nz = pd.DataFrame({f: (zc[f] if R.DIR[f] > 0 else -zc[f]) for f in R.ALL_IND})
PSz = pd.DataFrame({p: Nz[list(fl)].mean(axis=1) for p, fl in R.PILLARS.items()})
sz = R.agg(PSz, R.W_BUSINESS)
print("    z-score instead of min-max : Spearman vs headline = %.4f | "
      "top-50 overlap = %d/50"
      % (stats.spearmanr(sz, R.scores["mai_overall"]).statistic,
         len(top50 & set(sz.rank(ascending=False).nsmallest(50).index))))
sg = R.scores["mai_overall_geom"]
print("    geometric instead of arith : Spearman vs headline = %.4f | "
      "top-50 overlap = %d/50"
      % (stats.spearmanr(sg, R.scores["mai_overall"]).statistic,
         len(top50 & set(sg.rank(ascending=False).nsmallest(50).index))))
shifts = {}
for f in R.ALL_IND:
    ps2 = pd.DataFrame({p: R.N[[x for x in fl if x != f]].mean(axis=1)
                        for p, fl in R.PILLARS.items() if [x for x in fl if x != f]})
    s2 = R.agg(ps2, {k: R.W_BUSINESS[k] for k in ps2.columns})
    shifts[f] = (s2.rank(ascending=False) - R.scores["rank_overall"]).abs().max()
print("\n  leave-one-indicator-out, max |rank shift| (top 6):")
print(pd.Series(shifts).sort_values(ascending=False).head(6).to_string())
print("  -> a single indicator can move a district by %d of %d ranks."
      % (max(shifts.values()), len(PS)))

# ------------------------------------------------------------ ageing gap
sec("G. INDICATOR-COVERAGE GAPS vs THE CASE BRIEF")
one = next(iter(ind.values()))["nfhs"]["2019_20"]
avail = sorted(one)
print("  NFHS fields available per district in Firestore: %d" % len(avail))
print("  Fields the brief explicitly names, and whether the model uses them:")
brief = {
    "patient-to-doctor ratio / doctor density": "ABSENT from every source",
    "macroeconomic indicators": "SECC income dropped at the 80% coverage gate",
    "healthcare spending": "avg_delivery_exp_phf only (a maternity proxy)",
    "elderly / ageing population share": "ABSENT — no age band above 15 anywhere",
    "urbanisation": "urban_share (2011 vintage)",
    "income growth": "ABSENT — no time-varying income series",
}
for k, v in brief.items():
    print("    %-42s %s" % (k, v))
print("\n  Age structure actually present: %s"
      % [f for f in avail if "pop" in f or "age" in f or "15" in f])
