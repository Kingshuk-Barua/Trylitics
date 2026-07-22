"""Business-outcome metrics the submission currently has none of: decile lift,
coverage-vs-opportunity curve, and the head-to-head 'deploy by MAI vs deploy
by population' comparison. Also the wealth-proxy residual test.

These are the Deliverable-2 layer-3 metrics, computed on the CURRENT index so
the baseline is honest.

    python3 analysis/audit/06_business_metrics.py
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
sec = lambda t: print("\n" + "=" * 90 + "\n" + t + "\n" + "=" * 90)  # noqa: E731

S, PS, X, meta = R.scores, R.pillar_scores, R.X, R.meta
df = S.join(meta)

# A defensible stand-in for district pharma value, built only from things that
# are NOT in the index: population x an independent affluence signal. Stated as
# a proxy, not truth.
df = df[df["population"].notna()].copy()
sec("A. OPPORTUNITY PROXY (population x revealed private-market activity)")
priv = R.base["hosp_private_per_lakh"].reindex(df.index)
tbp = R.base["tb_private_share"].reindex(df.index)
z = pd.DataFrame({"a": priv, "b": tbp})
z = (z - z.mean()) / z.std()
activity = z.mean(axis=1)
df["opportunity"] = df["population"] * (activity - activity.min() + 0.5)
df["opportunity"] = df["opportunity"].fillna(df["opportunity"].median())
df["opportunity"] /= df["opportunity"].sum()
print("  proxy = population x normalised private-market activity "
      "(private hospitals/lakh, TB private notification share)")
print("  NOTE: both components are ALSO index inputs, so this proxy is")
print("  contaminated. It is a baseline placeholder, not a validation target —")
print("  see the uplift plan for the uncontaminated replacements.")
print("  districts with a usable proxy: %d" % len(df))


def gains(order_col, n_list=(50, 100, 200, 300)):
    o = df.sort_values(order_col, ascending=False)
    return {n: 100 * o["opportunity"].head(n).sum() for n in n_list}


sec("B. DECILE LIFT / GAINS — share of proxy opportunity captured by top-N")
rankers = {
    "MAI overall (current index)": df["mai_overall"],
    "Population alone": df["population"],
    "MAI chronic": df["mai_chronic"],
    "MAI acute": df["mai_acute"],
    "Random (expected)": None,
}
rows = []
for name, col in rankers.items():
    if col is None:
        rows.append({"ranking": name, **{f"top{n}": 100 * n / len(df)
                                         for n in (50, 100, 200, 300)}})
        continue
    df["_o"] = col
    g = gains("_o")
    rows.append({"ranking": name, **{f"top{n}": v for n, v in g.items()}})
print(pd.DataFrame(rows).set_index("ranking").round(1).to_string())
print("\n  Lift over random at top-100:")
for name, col in rankers.items():
    if col is None:
        continue
    df["_o"] = col
    print("    %-30s %.2fx" % (name, gains("_o")[100] / (100 * 100 / len(df))))

sec("C. THE HEADLINE BUSINESS CLAIM, TESTED HONESTLY")
df["_o"] = df["mai_overall"]
mai100 = gains("_o")[100]
df["_o"] = df["population"]
pop100 = gains("_o")[100]
print("  Deploy to top-100 by MAI        -> captures %.1f%% of proxy opportunity" % mai100)
print("  Deploy to top-100 by population -> captures %.1f%% of proxy opportunity" % pop100)
print("  Difference: %+.1f pp  (%+.1f%% relative)"
      % (mai100 - pop100, 100 * (mai100 / pop100 - 1)))
print("\n  >>> The current index UNDERPERFORMS naive population ranking on its")
print("  >>> own business objective. This is the single most damaging fact in")
print("  >>> the audit and the deck cannot make a top-N deployment claim until")
print("  >>> it is fixed.")
ov = len(set(df.nlargest(100, "mai_overall").index)
         & set(df.nlargest(100, "population").index))
print("\n  overlap between the two top-100 lists: %d/100 districts" % ov)

sec("D. COVERAGE-vs-COST CURVE (districts covered -> opportunity captured)")
for name, col in [("MAI overall", "mai_overall"), ("Population", "population")]:
    o = df.sort_values(col, ascending=False)
    cum = o["opportunity"].cumsum() * 100
    pts = [50, 100, 150, 200, 300, 400, 500]
    print("  %-12s " % name + " ".join("n=%d:%.0f%%" % (n, cum.iloc[n - 1]) for n in pts))
print("\n  districts needed to reach 50%% of proxy opportunity:")
for name, col in [("MAI overall", "mai_overall"), ("Population", "population")]:
    o = df.sort_values(col, ascending=False)
    cum = o["opportunity"].cumsum()
    print("    %-12s %d districts" % (name, int((cum < .5).sum()) + 1))

sec("E. WEALTH-PROXY RESIDUAL TEST (does the index add anything over income?)")
# The best income-like signal available in-repo: SECC monthly income >10k share
# (dropped from the index at the coverage gate, so it is genuinely external).
inc = R.base["inc_gt10k_share"].dropna()
common = inc.index.intersection(S.index)
print("  SECC mon_inc_gt_10k share available for %d of %d scored districts"
      % (len(common), len(S)))
for c in ["mai_overall", "mai_chronic", "mai_acute"]:
    r = stats.spearmanr(S.loc[common, c], inc.loc[common]).statistic
    print("    Spearman(%s, SECC income share) = %+.4f" % (c, r))
A = np.column_stack([np.ones(len(common)), inc.loc[common].values])
y = S.loc[common, "mai_overall"].values
beta = np.linalg.lstsq(A, y, rcond=None)[0]
res = y - A @ beta
r2 = 1 - res.var() / y.var()
print("\n  OLS mai_overall ~ SECC income share: R2 = %.3f" % r2)
print("  residual information content = %.1f%% of index variance" % (100 * (1 - r2)))
print("  PASS BAR proposed in the uplift plan: 0.30 <= R2 <= 0.65.")
print("  Verdict: %s" % ("PASS — the index is neither an income clone nor "
                         "unrelated to income" if 0.30 <= r2 <= 0.65 else
                         "REVIEW — outside the proposed band"))

sec("F. SPATIAL AUTOCORRELATION — why a random train/test split would lie")
st = meta["state_name"]
for c in ["mai_overall", "mai_chronic", "mai_acute"]:
    v = S[c]
    grand = v.var()
    within = v.groupby(st).transform("mean")
    between_r2 = 1 - (v - within).var() / grand
    print("  %-12s share of variance explained by STATE alone: %.1f%%"
          % (c, 100 * between_r2))
print("  -> a random district-level split leaks state identity into the test")
print("     fold. Any classifier must be blocked by state (see Deliverable 3).")
