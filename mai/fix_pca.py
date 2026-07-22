"""Re-aggregate Census PCA from the raw CKAN pull with the corrected level rule.

Audit finding C-04: `PcaAgg` picked one administrative level per
(district, rural_urban, gender) preferring Village > Town > Ward, on the
assumption that Town and Ward are the same population at two granularities.
Measured over the full raw pull that is false — Ward is the complete urban
enumeration and Town is a truncated subset (Ward >= Town in 686/686 pairs).

This script applies `max` across levels and writes
`analysis/audit/_cache/pca_fixed.json`, which `mai.data.load_pca_repaired`
overlays on the published documents.

    python3 -m mai.fix_pca

Requires the raw pull: `python3 -m pipeline.run --source idp_pca --no-publish`
"""
import collections
import glob
import gzip
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "analysis" / "audit" / "_cache"
CENSUS_2011_TOTAL = 1210854977

CUTS = ("age", "social_group", "literacy", "working_status",
        "worker_type", "occupation")

# Absent from the IDP mirror entirely; published Census 2011 district totals.
BACKFILL = {
    "482": ("Mumbai", "Maharashtra", 3085411),
    "483": ("Mumbai Suburban", "Maharashtra", 9356962),
    "315": ("Kolkata", "West Bengal", 4496694),
}


def _isnan(v):
    return v is None or str(v).strip().lower() in {"nan", "none", "", "null"}


def _metric(r):
    active = [c for c in CUTS if not _isnan(r.get(c))]
    if active == ["social_group"] and str(r["social_group"]).lower() == "total":
        return "pop"
    if active == ["literacy"] and str(r["literacy"]).lower() == "literate":
        return "literate"
    if active == ["age"] and "0_to_6" in str(r["age"]).lower():
        return "pop_0_6"
    return None


def main():
    files = sorted(glob.glob(str(ROOT / "data/raw/idp_pca/ingest_*/page_*.json.gz")))
    if not files:
        raise SystemExit("no raw PCA pages found — run "
                         "`python3 -m pipeline.run --source idp_pca --no-publish`")
    buckets = collections.defaultdict(lambda: collections.defaultdict(float))
    names = {}
    for f in files:
        with gzip.open(f, "rt") as fh:
            recs = json.load(fh)["result"]["records"]
        for r in recs:
            m = _metric(r)
            if m is None:
                continue
            code = str(r.get("district_code", "")).strip()
            if not code or _isnan(code):
                continue
            try:
                pop = float(r.get("population") or 0)
            except (TypeError, ValueError):
                continue
            ru = str(r.get("rural_urban", "")).strip() or "Unknown"
            gen = str(r.get("gender", "")).strip() or "Unknown"
            lvl = str(r.get("level", "")).strip() or "Unknown"
            buckets[(code, ru, gen, m)][lvl] += pop
            names.setdefault(code, (r.get("district_name"), r.get("state_name")))

    docs = collections.defaultdict(dict)
    for (code, ru, gen, m), by_level in buckets.items():
        key = "{}_{}_{}".format(m, ru.lower(), gen.lower())
        docs[code][key] = docs[code].get(key, 0) + max(by_level.values())

    out = {}
    for code, sums in docs.items():
        nm, st = names.get(code, (None, None))
        doc = dict(sums)
        doc["district_name"] = nm
        doc["state_name"] = st
        doc["population_source"] = "idp_pca_mirror_max_levels"
        tot = sum(v for k, v in sums.items()
                  if k.startswith("pop_") and k.endswith("_total")
                  and not k.startswith("pop_0_6"))
        if tot:
            doc["population_2011_total"] = int(tot)
        out[code] = doc

    for code, (nm, st, pop) in BACKFILL.items():
        if code in out and out[code].get("population_2011_total"):
            continue
        out[code] = {"district_name": nm, "state_name": st,
                     "population_2011_total": pop,
                     "population_source": "census_2011_backfill"}

    total = sum(d.get("population_2011_total", 0) for d in out.values())
    CACHE.mkdir(parents=True, exist_ok=True)
    with open(CACHE / "pca_fixed.json", "w") as f:
        json.dump(out, f)

    print("districts written        : %d" % len(out))
    print("population total         : %d" % total)
    print("as %% of Census 2011      : %.1f%%" % (100 * total / CENSUS_2011_TOTAL))
    print("backfilled districts     : %s"
          % [c for c in BACKFILL if out[c]["population_source"] == "census_2011_backfill"])
    for c in ("507", "568", "525", "013", "482", "315"):
        if c in out:
            print("  %-4s %-18s %12d  (%s)"
                  % (c, out[c].get("district_name"),
                     out[c].get("population_2011_total", 0),
                     out[c]["population_source"]))


if __name__ == "__main__":
    main()
