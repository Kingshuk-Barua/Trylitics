"""Deep probes on (a) the census_pca population defect that sinks Mumbai/Kolkata
and shrinks Hyderabad, and (b) the excluded nfhs5_factsheet's real state.

    python3 analysis/audit/05_population_and_factsheet.py
"""
import importlib
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
R = importlib.import_module("02_rebuild_index")
pd.set_option("display.width", 220)
sec = lambda t: print("\n" + "=" * 90 + "\n" + t + "\n" + "=" * 90)  # noqa: E731

pca = R.fs_pca

sec("A1. Are Mumbai / Kolkata even present in census_pca?")
for code in ["482", "483", "315", "507", "700", "599", "601", "257", "753"]:
    d = pca.get(code)
    nm = (R.fs_ind.get(code) or {}).get("district_name")
    if d is None:
        print("  code %-4s %-18s -> ABSENT from census_pca entirely" % (code, nm))
    else:
        ks = sorted(k for k in d if k.startswith(("pop_", "literate_")))
        print("  code %-4s %-18s pop=%-10s keys=%s"
              % (code, d.get("district_name"), d.get("population_2011_total"), ks))

sec("A2. Hyderabad — why is the population 224,672 instead of ~3.94 million?")
h = pca.get("507")
if h:
    for k, v in sorted(h.items()):
        print("   %-26s %s" % (k, v))

sec("A3. How many census_pca docs are missing a rural or an urban side?")
miss_u = [k for k, v in pca.items() if v.get("pop_urban_total") is None]
miss_r = [k for k, v in pca.items() if v.get("pop_rural_total") is None]
print("  missing pop_urban_total: %d | missing pop_rural_total: %d" % (len(miss_u), len(miss_r)))
print("  missing-urban examples :", [(c, pca[c].get("district_name")) for c in miss_u[:8]])
print("  missing-rural examples :", [(c, pca[c].get("district_name")) for c in miss_r[:8]])
print("\n  For a missing-URBAN district, urban_share evaluates to None and is")
print("  then imputed to the state median -- a 100%-rural district can inherit")
print("  an urban share it does not have, and vice versa.")
ur_imp = R.imputed["urban_share"].sum() if "urban_share" in R.imputed else 0
print("  urban_share cells imputed in the scored set: %d" % ur_imp)

sec("A4. Population sanity against Census 2011 for the 20 largest districts")
known = {  # Census 2011 published district totals (millions), for spot-check
    "Thane": 11.06, "Pune": 9.43, "Mumbai Suburban": 9.36, "Bangalore": 9.62,
    "Ahmadabad": 7.21, "Chennai": 4.65, "Hyderabad": 3.94, "Mumbai": 3.09,
    "Kolkata": 4.50, "Surat": 6.08,
}
rows = []
for c, v in pca.items():
    n = v.get("district_name")
    if n in known:
        rows.append({"code": c, "district": n, "pipeline_pop": v.get("population_2011_total"),
                     "census_2011": int(known[n] * 1e6)})
df = pd.DataFrame(rows)
if not df.empty:
    df["ratio"] = (df["pipeline_pop"] / df["census_2011"]).round(3)
    print(df.sort_values("ratio").to_string(index=False))
print("\n  Districts present in census_pca but ABSENT from the checks above are")
print("  absent from the collection altogether:",
      [n for n in known if n not in set(df["district"])] if not df.empty else known)

sec("B. nfhs5_factsheet — numeric coercion done properly")
fs = R.load("nfhs5_factsheet")
fdf = pd.DataFrame(fs).T
num = fdf.apply(pd.to_numeric, errors="coerce")
num = num.loc[:, num.notna().sum() > 0]
print("  707 docs | numeric-coercible fields: %d" % num.shape[1])
neg = []
for c in num.columns:
    v = num[c].dropna()
    if len(v) and (v < 0).any():
        neg.append((c, 100 * (v < 0).mean(), v.min(), v.max()))
neg.sort(key=lambda x: -x[1])
print("  fields containing NEGATIVE values: %d of %d" % (len(neg), num.shape[1]))
print("  %-44s %8s %10s %10s" % ("field", "%neg", "min", "max"))
for c, p, mn, mx in neg[:18]:
    print("  %-44s %7.1f%% %10.1f %10.1f" % (c, p, mn, mx))

print("\n  Cross-check: the same concept in district_indicators (used by the model)")
pairs = [("anaemic_children_6_59_months", "child_6_59_anemic"),
         ("institutional_birth", "dc_insti_births"),
         ("household_electricity", "pop_hh_elec"),
         ("literate_women", "fem_literacy")]
for fsk, idk in pairs:
    a = num[fsk].dropna() if fsk in num else pd.Series(dtype=float)
    b = pd.Series({k: (v.get("nfhs", {}).get("2019_20", {}) or {}).get(idk)
                   for k, v in R.fs_ind.items()}).dropna()
    print("   %-32s factsheet[min=%7.1f med=%6.1f]  indicators[min=%6.1f med=%6.1f]"
          % (fsk, a.min() if len(a) else np.nan, a.median() if len(a) else np.nan,
             b.min() if len(b) else np.nan, b.median() if len(b) else np.nan))

print("\n  Unique fields the factsheet offers that the model has no equivalent for:")
for c in ["out_of_pocket_expenditure", "women_cervical_cancer", "women_breast_cancer",
          "women_oral_cancer", "sex_ratio", "women_very_high_sugar",
          "men_very_high_sugar", "women_high_sugar_control_with_medicine",
          "men_high_sugar_control_with_medicine", "population_below_15years"]:
    if c in num:
        v = num[c].dropna()
        print("    %-42s n=%3d median=%9.1f negatives=%3d"
              % (c, len(v), v.median(), int((v < 0).sum())))
