"""Build the offline fallback bundle for the web app.

The app reads Firestore at runtime. This script produces the payload it falls
back to when Firestore is unreachable (no web config, offline demo, judge on a
plane), plus the analysis artefacts that are NOT in Firestore at all — the
validation table, benchmark pack, ML falsification, coverage, imputation
sensitivity, crosswalk review and the GenAI evaluations all live only in
`analysis/audit/_cache/v2/`.

District documents are built to exactly the schema `mai/publish.py` writes, so
the fallback and the live read are the same shape and the UI has one contract.

Read-only with respect to everything outside `web/public/data/`.

    python3 web/scripts/build_fallback.py
"""
import json
import math
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "analysis" / "audit" / "_cache"
V2 = CACHE / "v2"
OUT = ROOT / "web" / "public" / "data"

sys.path.insert(0, str(ROOT))


def clean(o):
    """NaN is not JSON. Convert to null rather than emitting `NaN` literals."""
    if isinstance(o, float):
        return None if (math.isnan(o) or math.isinf(o)) else round(o, 6)
    if isinstance(o, dict):
        return {str(k): clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean(v) for v in o]
    if hasattr(o, "item"):
        return clean(o.item())
    return o


def write(name, obj):
    OUT.mkdir(parents=True, exist_ok=True)
    p = OUT / name
    with open(p, "w") as f:
        json.dump(clean(obj), f, separators=(",", ":"))
    print("  %-28s %8.1f KB" % (name, p.stat().st_size / 1024))


def csv_records(path, **kw):
    if not path.exists():
        return []
    return pd.read_csv(path, **kw).to_dict(orient="records")


def main():
    from mai import publish as P                                # noqa: E402

    print("building fallback bundle -> %s" % OUT)

    # --- 1. district documents, identical in shape to the Firestore payload
    docs, run = P.build_documents()
    write("districts.json", {"generated_from": "analysis/audit/_cache/v2",
                             "model_version": run["model_version"],
                             "count": len(docs), "docs": docs})
    write("run.json", run)

    # --- 2. validation and evidence artefacts (Firestore holds none of these)
    val = csv_records(V2 / "validation_v2.csv")
    write("validation.json", {"rows": val,
                              "pass": sum(1 for r in val if r["verdict"] == "PASS"),
                              "fail": sum(1 for r in val if r["verdict"] == "FAIL")})

    bench = {}
    if (V2 / "benchmarks_v2.json").exists():
        bench = json.load(open(V2 / "benchmarks_v2.json"))
    write("benchmarks.json", bench)

    if (V2 / "ml_validation_v2.json").exists():
        write("ml.json", json.load(open(V2 / "ml_validation_v2.json")))

    # --- 3. data quality
    cov = csv_records(V2 / "coverage_report_v2.csv")
    cw = pd.read_csv(V2 / "crosswalk_review_v2.csv") if (
        V2 / "crosswalk_review_v2.csv").exists() else pd.DataFrame()
    cw_summary = (cw["category"].value_counts().to_dict() if len(cw) else {})
    # the full review file is 500+ rows; ship it, it is the audit trail
    write("data_quality.json", {
        "coverage": cov,
        "crosswalk_summary": cw_summary,
        "crosswalk_rows": cw.fillna("").to_dict(orient="records") if len(cw) else [],
        "imputation": run["imputation"],
        "reproducibility": (json.load(open(V2 / "reproducibility_v2.json"))
                            if (V2 / "reproducibility_v2.json").exists() else {}),
        "reproducibility_detail": csv_records(V2 / "reproducibility_v2.csv"),
        "staleness": csv_records(V2 / "staleness_v2.csv"),
        "imputation_spearman": (
            pd.read_csv(V2 / "imputation_spearman_v2.csv", index_col=0)
              .to_dict() if (V2 / "imputation_spearman_v2.csv").exists() else {}),
    })

    # per-district imputation flags, keyed exactly as the docs are
    if (V2 / "imputation_flags_v2.json").exists():
        write("imputation_flags.json",
              json.load(open(V2 / "imputation_flags_v2.json")))

    # --- 4. GenAI layer
    g = V2 / "genai"
    genai = {}
    if (g / "g1_eval_summary.json").exists():
        genai["g1_summary"] = json.load(open(g / "g1_eval_summary.json"))
    if (g / "g1_eval.csv").exists():
        genai["g1_rows"] = pd.read_csv(g / "g1_eval.csv").fillna("").to_dict(
            orient="records")
    if (g / "g2_narratives.json").exists():
        n = json.load(open(g / "g2_narratives.json"))
        genai["g2_count"] = len(n)
        genai["g2_llm"] = sum(1 for v in n.values() if v.get("source") == "llm")
        genai["g2_rejected"] = [
            {"code": k, "rejected_numbers": v.get("rejected_numbers"),
             "draft": v.get("llm_draft", "")[:400]}
            for k, v in n.items() if v.get("source") == "template_fallback"]
        genai["g2_samples"] = [
            {"code": k, "narrative": v["narrative"], "model": v.get("model")}
            for k, v in list(n.items())[:8] if v.get("source") == "llm"]
    if (g / "g2_judge_summary.json").exists():
        genai["g2_judge"] = json.load(open(g / "g2_judge_summary.json"))
    if (g / "g1_resolutions.csv").exists():
        genai["g1_resolutions"] = pd.read_csv(
            g / "g1_resolutions.csv").fillna("").to_dict(orient="records")
    write("genai.json", genai)

    # --- 5. pillar-level indicator detail for the methodology page
    write("methodology.json", {
        "method": run["method"],
        "alpha": run["alpha"], "alpha_future": run["alpha_future"],
        "quality_weights": run["quality_weights"],
        "index_pillars": run["index_pillars"],
        "pillar_composition": run["pillar_composition"],
        "indicator_directions": run["indicator_directions"],
        "indicators_kept": run["indicators_kept"],
        "indicators_dropped": run["indicators_dropped_below_coverage"],
        "data_vintage": run["data_vintage"],
        "seed": run["seed"], "git_sha": run["git_sha"],
        "nfhs4_sentinel_fields": run["nfhs4_sentinel_fields"],
        "n_districts": run["n_districts"], "n_indicators": run["n_indicators"],
    })

    print("done.")


if __name__ == "__main__":
    main()
