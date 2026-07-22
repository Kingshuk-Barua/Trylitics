"""Head-to-head: published v1 scores vs rebuilt v2, on the audit's own metrics.

    python3 analysis/audit/07_v1_vs_v2.py
"""
import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
CACHE = ROOT / "analysis" / "audit" / "_cache"
pd.set_option("display.width", 220)

v1 = pd.DataFrame(pickle.load(open(CACHE / "mai_scores.pkl", "rb"))).T
for c in ("overall_rank", "chronic_rank", "acute_rank",
          "overall_score", "chronic_score", "acute_score"):
    v1[c] = pd.to_numeric(v1[c], errors="coerce")
v2 = pd.read_csv(CACHE / "v2" / "scores_v2_with_intervals.csv", index_col=0)
v2.index = [str(i).zfill(3) for i in v2.index]
v1.index = [str(i).zfill(3) for i in v1.index]
sec = lambda t: print("\n" + "=" * 100 + "\n" + t + "\n" + "=" * 100)  # noqa: E731

sec("FACE VALIDITY — where the major pharma markets rank")
probe = ["mumbai", "mumbai suburban", "thane", "pune", "bengaluru urban",
         "ahmadabad", "surat", "kolkata", "chennai", "hyderabad", "lucknow",
         "jaipur", "nagpur", "kanpur nagar", "patna", "indore", "ludhiana",
         "east", "north west"]
rows = []
for code in v2.index:
    nm = str(v2.loc[code, "district_name"]).lower()
    if nm in probe:
        rows.append({
            "district": v2.loc[code, "district_name"],
            "state": v2.loc[code, "state_name"],
            "population": v2.loc[code, "population"],
            "v1_rank": int(v1.loc[code, "overall_rank"]) if code in v1.index else None,
            "v2_rank": int(v2.loc[code, "rank_overall"]),
        })
df = pd.DataFrame(rows)
df["change"] = df["v1_rank"] - df["v2_rank"]
print(df.sort_values("v2_rank").to_string(index=False))

sec("TOP 20 — v1 vs v2")
t1 = v1.nsmallest(20, "overall_rank")[["district_name", "state_name", "overall_rank"]]
t2 = v2.nsmallest(20, "rank_overall")[["district_name", "state_name",
                                       "population", "rank_overall"]]
print("v1:"); print(t1.to_string(index=False))
print("\nv2:"); print(t2.to_string(index=False))
print("\n  Delhi districts in the top 50: v1=%d  v2=%d"
      % ((v1.nsmallest(50, "overall_rank")["state_name"] == "Delhi").sum(),
         (v2.nsmallest(50, "rank_overall")["state_name"] == "Delhi").sum()))

sec("THE AUDIT'S FAILING METRICS, v1 vs v2")
pop2 = v2["population"].astype(float)
comp = []


def spear(a, b):
    return stats.spearmanr(a, b, nan_policy="omit").statistic


common = v1.index.intersection(v2.index)
comp.append(("Spearman(index, population)",
             spear(v1.loc[common, "overall_score"].astype(float), pop2.loc[common]),
             spear(v2.loc[common, "mai_overall"], pop2.loc[common]), "higher"))
comp.append(("Spearman(overall, chronic)",
             spear(v1["overall_score"].astype(float), v1["chronic_score"].astype(float)),
             spear(v2["mai_overall"], v2["mai_chronic"]), "lower"))
comp.append(("Spearman(chronic, acute)",
             spear(v1["chronic_score"].astype(float), v1["acute_score"].astype(float)),
             spear(v2["mai_chronic"], v2["mai_acute"]), "lower"))
comp.append(("Spearman(current, future)",
             np.nan, spear(v2["mai_current"], v2["mai_future"]), "lower"))
comp.append(("index observed range (of 100)",
             v1["overall_score"].astype(float).max() - v1["overall_score"].astype(float).min(),
             v2["mai_overall"].max() - v2["mai_overall"].min(), "higher"))
comp.append(("index sd",
             v1["overall_score"].astype(float).std(), v2["mai_overall"].std(), "higher"))
g1 = np.median(np.abs(np.diff(v1["overall_score"].astype(float).sort_values(ascending=False).values)))
g2 = np.median(np.abs(np.diff(v2["mai_overall"].sort_values(ascending=False).values)))
comp.append(("median adjacent-rank score gap", g1, g2, "higher"))
out = pd.DataFrame(comp, columns=["metric", "v1", "v2", "better"])
print(out.round(4).to_string(index=False))

sec("PILLAR / SIZE DIAGNOSTICS (v2)")
print("  Spearman(size_score, population) = %.4f"
      % spear(v2["size_score"], pop2))
print("  districts scored on an imputed population: %d"
      % int(v2["population"].isna().sum()))
print("\n  v2 tier sizes:", v2["tier"].value_counts().sort_index().to_dict())
print("  growth_flag districts:", int(v2["growth_flag"].sum()))
