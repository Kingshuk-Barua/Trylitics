"""R-12 — external convergent-validity benchmarks.

The point of Layer 2 is that NONE of these are model inputs. What is actually
reachable, and what is not, matters as much as the correlations:

  AVAILABLE
    NITI Aayog State Health Index, Round 4 (2019-20) composite scores.
      State level. Published subset only — see NITI_SHI_R4 below for exactly
      which states and why it is partial.
    SECC monthly-income>10k share. District level, 622 scored districts.
      Genuinely external because it was DROPPED from v1 at the coverage gate;
      it re-enters P4 in v2, so it is external to v1 and internal to v2. Both
      readings are reported.

  BLOCKED, and why (recorded rather than quietly skipped)
    District NSDP        — not on India Data Portal (searched: 'district
                           domestic product', 'GDDP', 'per capita income
                           district' — 0 usable resources). State DES portals
                           publish inconsistently and would need per-state
                           scraping.
    SHRUG night lights   — devdatalab.org requires a human to pick tables; the
                           S3 bucket refuses listing and guessed object paths
                           return 403. `config.SOURCES['shrug']` already
                           encodes this as a manual step. Drop a CSV at
                           analysis/audit/_cache/external/nightlights.csv with
                           columns district_code,radiance and this module picks
                           it up automatically.
    IQVIA state IPM      — commercial.

Any benchmark file that appears in _cache/external/ is used; anything absent is
reported as UNAVAILABLE, never silently omitted from the pass/fail tally.

    python3 -m mai.benchmarks
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mai import data as D                      # noqa: E402
from mai.crosswalk import norm_state           # noqa: E402

EXTERNAL = D.CACHE / "external"
OUT = D.CACHE / "v2"

# NITI Aayog "Healthy States, Progressive India" State Health Index Round IV
# (reference year 2019-20), OVERALL composite performance score.
#
# PARTIAL BY NECESSITY. NITI's own ranking portal (social.niti.gov.in) refuses
# connections and the full report PDF exceeds the fetch limit, so only the
# scores quoted in secondary coverage of the release are recorded here. Every
# value below traces to a published figure; no value is interpolated. n=11 is
# small for a rank correlation and the result is reported with that caveat
# rather than dressed up.
#
# Sources:
#   https://www.pib.gov.in/PressReleasePage.aspx?PRID=1785506  (release)
#   https://www.odisha.plus/2021/12/niti-aayog-health-index-2019-20/
#   https://www.twenty22.in/2021/12/niti-health-index-2019-20.html
NITI_SHI_R4 = {
    # Larger states
    "kerala": 82.20,
    "tamil nadu": 72.42,
    "telangana": 69.96,
    "andhra pradesh": 69.95,
    "uttar pradesh": 30.57,
    # Smaller states
    "mizoram": 75.77,
    "tripura": 70.16,
    "nagaland": 27.00,
    # Union territories
    "chandigarh": 62.53,
    "andaman and nicobar islands": 44.74,
}
NITI_SHI_ROUND = "Round IV, reference year 2019-20, overall composite score"


def load_optional(name, cols):
    """Load an external benchmark CSV if a human has supplied one."""
    p = EXTERNAL / (name + ".csv")
    if not p.exists():
        return None
    df = pd.read_csv(p, dtype={"district_code": str})
    missing = [c for c in cols if c not in df.columns]
    if missing:
        raise ValueError("%s is missing columns %s" % (p, missing))
    if "district_code" in df.columns:
        df["district_code"] = df["district_code"].str.zfill(3)
        df = df.set_index("district_code")
    return df


def band(name, value, lo, hi, n=None, note=""):
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return {"benchmark": name, "spearman": None, "n": n,
                "verdict": "UNAVAILABLE", "band": "%.2f-%.2f" % (lo, hi),
                "note": note}
    return {"benchmark": name, "spearman": round(float(value), 4), "n": n,
            "verdict": "PASS" if lo <= value <= hi else "FAIL",
            "band": "%.2f-%.2f" % (lo, hi), "note": note}


def run(scores, scored, meta, pillar_scores):
    rows = []
    sec = lambda t: print("\n" + "=" * 96 + "\n" + t + "\n" + "=" * 96)  # noqa: E731

    sec("R-12 · EXTERNAL CONVERGENT VALIDITY")

    # ---- 1. NITI State Health Index (state level) -------------------------
    st = meta["state_name"].map(norm_state)
    state_mai = scores["mai_overall"].groupby(st).mean()
    niti = pd.Series(NITI_SHI_R4)
    common = state_mai.index.intersection(niti.index)
    r_niti = (stats.spearmanr(state_mai[common], niti[common]).statistic
              if len(common) >= 4 else None)
    rows.append(band(
        "NITI State Health Index R4 (state)", r_niti, 0.30, 0.65, len(common),
        "published subset only; n is small — treat as indicative"))
    print("  states matched: %d of %d published — %s"
          % (len(common), len(niti), sorted(common)))
    if r_niti is not None:
        tbl = pd.DataFrame({"mean_MAI": state_mai[common].round(2),
                            "NITI_SHI": niti[common]}).sort_values(
                                "NITI_SHI", ascending=False)
        print(tbl.to_string())
        print("\n  Spearman(mean MAI, NITI SHI) = %+.4f   band 0.30-0.65 -> %s"
              % (r_niti, rows[-1]["verdict"]))
        print("  reading: >0.75 would mean the MAI is a health-system-")
        print("  performance clone; <0.20 would mean no construct overlap.")

    # ---- 2. SECC income (district level) ----------------------------------
    inc = scored["inc_gt10k_share"].dropna()
    idx = inc.index.intersection(scores.index)
    r_inc = stats.spearmanr(scores.loc[idx, "mai_overall"], inc.loc[idx]).statistic
    r_q = stats.spearmanr(scores.loc[idx, "quality_overall"], inc.loc[idx]).statistic
    r_p4 = stats.spearmanr(pillar_scores.loc[idx, "P4_afford"], inc.loc[idx]).statistic
    rows.append(band("SECC income share vs MAI (district)", r_inc, 0.35, 0.70,
                     len(idx), "composite level; size and quality offset"))
    rows.append(band("SECC income share vs QUALITY (district)", r_q, 0.35, 0.70,
                     len(idx), "the per-capita construct — meaningful level"))
    rows.append(band("SECC income share vs P4_afford (district)", r_p4, 0.50, 0.95,
                     len(idx), "proves the R-02 join repair landed"))

    # ---- 3. Night lights / NSDP, if supplied ------------------------------
    nl = load_optional("nightlights", ["district_code", "radiance"])
    if nl is not None:
        j = nl.join(scores[["mai_overall"]], how="inner").join(
            meta[["population"]])
        per_cap = j["radiance"] / j["population"].replace(0, np.nan)
        r_nl = stats.spearmanr(j["mai_overall"], per_cap,
                               nan_policy="omit").statistic
        rows.append(band("Night-lights radiance per capita (district)",
                         r_nl, 0.40, 0.75, len(j), "SHRUG/VIIRS"))
    else:
        rows.append(band("Night-lights radiance per capita (district)", None,
                         0.40, 0.75, None,
                         "BLOCKED: SHRUG needs a manual table pick; drop "
                         "_cache/external/nightlights.csv to enable"))

    nsdp = load_optional("district_nsdp", ["district_code", "nsdp_per_capita"])
    if nsdp is not None:
        j = nsdp.join(scores[["mai_overall"]], how="inner")
        r_ns = stats.spearmanr(j["mai_overall"], j["nsdp_per_capita"]).statistic
        rows.append(band("District NSDP per capita", r_ns, 0.35, 0.70, len(j)))
    else:
        rows.append(band("District NSDP per capita", None, 0.35, 0.70, None,
                         "BLOCKED: not published district-wise on IDP/data.gov.in"))

    # ---- 4. wealth-proxy residual test ------------------------------------
    sec("WEALTH-PROXY RESIDUAL TEST")
    A = np.column_stack([np.ones(len(idx)), inc.loc[idx].values])
    y = scores.loc[idx, "mai_overall"].values
    beta = np.linalg.lstsq(A, y, rcond=None)[0]
    resid = y - A @ beta
    r2 = 1 - resid.var() / y.var()
    revealed = scored.loc[idx, "tb_private_share"]
    r_resid = stats.spearmanr(resid, revealed, nan_policy="omit").statistic
    print("  R2(MAI ~ SECC income)                    = %.4f   band 0.30-0.65" % r2)
    print("  Spearman(income residual, revealed demand)= %+.4f  bar >= 0.20"
          % r_resid)
    print("  -> the index's non-income content carries independent signal: %s"
          % ("YES" if r_resid >= 0.20 else "NO"))
    rows.append({"benchmark": "R2(MAI ~ income)", "spearman": round(float(r2), 4),
                 "n": len(idx),
                 "verdict": "PASS" if 0.30 <= r2 <= 0.65 else "FAIL",
                 "band": "0.30-0.65",
                 "note": "composite level; decomposes into size vs quality"})
    rows.append({"benchmark": "Spearman(residual, revealed demand)",
                 "spearman": round(float(r_resid), 4), "n": len(idx),
                 "verdict": "PASS" if r_resid >= 0.20 else "FAIL",
                 "band": ">=0.20", "note": "non-income content must carry signal"})

    df = pd.DataFrame(rows)
    sec("SUMMARY")
    print(df.to_string(index=False))
    n_un = int((df["verdict"] == "UNAVAILABLE").sum())
    print("\n  %d PASS · %d FAIL · %d UNAVAILABLE (blocked sources are counted, "
          "not hidden)" % (int((df.verdict == "PASS").sum()),
                           int((df.verdict == "FAIL").sum()), n_un))

    OUT.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT / "benchmarks_v2.csv", index=False)
    with open(OUT / "benchmarks_v2.json", "w") as f:
        json.dump({"rows": rows, "niti_round": NITI_SHI_ROUND,
                   "niti_states_used": sorted(common)}, f, indent=2)
    return df


def main():
    from mai import features as F, impute as IM, index as IX
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
    scores = IX.add_ranks_and_tiers(scores, PS)
    meta = scored[["district_name", "state_name", "population"]]
    EXTERNAL.mkdir(parents=True, exist_ok=True)
    return run(scores, scored, meta, PS)


if __name__ == "__main__":
    main()
