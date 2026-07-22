#!/usr/bin/env python3
"""Run the whole MAI v2 chain: build -> validate -> ml -> benchmarks ->
narrative -> reproduce -> G1 -> G2 -> bundle locally -> publish to Firestore.

    python3 run_all.py                  # everything, Firestore step is a DRY RUN
    python3 run_all.py --confirm        # ... and actually write 699 documents
    python3 run_all.py --skip-genai     # no Groq calls at all
    python3 run_all.py --from validate  # resume after a failure
    python3 run_all.py --only bundle,publish
    python3 run_all.py --list           # show the steps and exit

Three rules this script keeps, because they are the ones that matter when a run
is automated rather than typed:

  1. FIRESTORE IS NEVER WRITTEN BY ACCIDENT. `mai.publish` is invoked without
     `--confirm` unless you pass `--confirm` here. The default run therefore
     produces every result locally and shows you what a publish WOULD do.

  2. THE GENAI STEPS CANNOT FAIL THE RUN. They are optional by design — a
     rate limit or a missing key degrades the output to the deterministic
     narrative templates, which is exactly what `mai.publish` falls back to.
     Everything before them is deterministic and IS allowed to fail the run.

  3. NOTHING IS PUBLISHED FROM A STALE BUILD. `mai.reproduce` runs before the
     publish step; if the inputs have drifted from what the scores were built
     from, the chain stops there rather than pushing scores that no longer
     match their own provenance.

Every step's output is streamed to the terminal and captured to
`logs/run_all_<timestamp>.log`.
"""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
V2 = ROOT / "analysis" / "audit" / "_cache" / "v2"
RESULTS = ROOT / "results"
LOGS = ROOT / "logs"

PY = sys.executable or "python3"


# --------------------------------------------------------------- the chain
# (name, argv, fatal-on-failure, one-line description)
def steps(args):
    rpm = args.rpm
    return [
        ("pull", [PY, "analysis/audit/00_pull_firestore.py"], True,
         "read-only Firestore snapshot -> _cache/*.pkl"),
        ("build", [PY, "-m", "mai.build"], True,
         "features -> pillars -> the three indices"),
        ("validate", [PY, "-m", "mai.validate"], True,
         "31 pre-registered tests + Monte-Carlo rank intervals"),
        ("ml", [PY, "-m", "mai.ml"], True,
         "supervised falsification, GroupKFold blocked by state"),
        ("benchmarks", [PY, "-m", "mai.benchmarks"], True,
         "external convergent validity (NITI SHI, SECC income)"),
        ("narrative", [PY, "-m", "mai.narrative"], True,
         "deterministic district briefs, numbers placed by code"),
        ("reproduce", [PY, "-m", "mai.reproduce", "--selftest"], True,
         "rebuild + compare at 2dp, and re-hash the inputs"),
        ("g1_eval", [PY, "-m", "mai.genai.g1_crosswalk", "--eval",
                     "--n", str(args.g1_n), "--rpm", str(rpm)], False,
         "G1: measure crosswalk precision on labelled cases"),
        ("g1_resolve", [PY, "-m", "mai.genai.g1_crosswalk", "--resolve",
                        "--rpm", str(rpm)], False,
         "G1: resolve the open crosswalk labels"),
        ("g2_generate", [PY, "-m", "mai.genai.g2_narrative", "--generate",
                         "--rpm", str(rpm)], False,
         "G2: write briefs, each checked by a numeric verifier"),
        ("g2_judge", [PY, "-m", "mai.genai.g2_narrative", "--judge",
                      "--n", str(args.g2_n), "--rpm", str(rpm)], False,
         "G2: blind A/B against the template control"),
        ("bundle", None, True,
         "copy every artefact to results/<run>/ with a manifest"),
        ("publish", None, True,
         "Firestore: 698 mai_scores + 1 mai_runs"),
    ]


GENAI = {"g1_eval", "g1_resolve", "g2_generate", "g2_judge"}
DEFAULT_SKIP = {"pull"}          # opt in with --pull; the snapshot is usually current


# ------------------------------------------------------------------ plumbing
class Tee:
    def __init__(self, path):
        self.f = open(path, "a", buffering=1)

    def write(self, s):
        sys.stdout.write(s)
        sys.stdout.flush()
        self.f.write(s)

    def close(self):
        self.f.close()


def rule(tee, char="-", text=""):
    tee.write("\n" + (text + " " if text else "") + char * max(4, 78 - len(text))
              + "\n")


def run(cmd, tee, cwd=ROOT):
    """Stream a subprocess to the terminal and the log. Returns (rc, seconds)."""
    t0 = time.time()
    p = subprocess.Popen(cmd, cwd=str(cwd), stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT, text=True, bufsize=1,
                         env={**os.environ, "PYTHONUNBUFFERED": "1"})
    for line in p.stdout:
        tee.write(line)
    p.wait()
    return p.returncode, time.time() - t0


def have_groq():
    """A key from any of the accepted places — the same resolution the client uses.

    Importing pipeline.config loads the repo's .env into os.environ, exactly as
    every subprocess does. Without this, a key that lives ONLY in .env (the
    normal case) is invisible here and the GenAI steps get wrongly skipped.
    """
    try:
        from pipeline import config as _cfg              # noqa: F401  (.env autoload)
    except Exception:                                    # noqa: BLE001
        pass
    if os.environ.get("GROQ_API_KEYS", "").strip():
        return True
    for n in ["GROQ_API_KEY"] + ["GROQ_API_KEY_%d" % i for i in range(2, 9)]:
        if os.environ.get(n, "").strip():
            return True
    return (ROOT / "Credentials" / "Groq.json").is_file()


# -------------------------------------------------------------------- bundle
def sha256(path, chunk=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(chunk), b""):
            h.update(b)
    return h.hexdigest()


def headline_numbers():
    """The few figures a reader checks first, read back from the artefacts."""
    import pandas as pd

    out = {}
    run_rec = json.loads((V2 / "run_v2.json").read_text())
    out["model_version"] = run_rec["model_version"]
    out["created_at"] = str(run_rec["created_at"])
    out["git_sha"] = run_rec.get("git_sha")
    out["n_districts"] = run_rec["n_districts"]
    out["n_indicators"] = run_rec["n_indicators"]
    out["imputed_pct"] = run_rec["imputation"]["imputed_pct"]

    val = pd.read_csv(V2 / "validation_v2.csv")
    out["tests_pass"] = int((val["verdict"] == "PASS").sum())
    out["tests_fail"] = int((val["verdict"] == "FAIL").sum())
    # Rows carrying a verdict are the tests; the rest are decompositions
    # reported alongside them and are not scored either way.
    out["tests_total"] = out["tests_pass"] + out["tests_fail"]
    out["informational_rows"] = int(len(val)) - out["tests_total"]
    out["failing_tests"] = val.loc[val["verdict"] == "FAIL", "metric"].tolist()

    sc = pd.read_csv(V2 / "scores_v2_with_intervals.csv", index_col=0)
    top = sc.nsmallest(1, "rank_overall").iloc[0]
    out["top_district"] = "%s, %s (%.1f)" % (top["district_name"],
                                             top["state_name"],
                                             top["mai_overall"])
    out["score_range"] = [round(float(sc["mai_overall"].min()), 1),
                          round(float(sc["mai_overall"].max()), 1)]

    p = V2 / "genai" / "g1_eval_summary.json"
    if p.exists():
        g1 = json.loads(p.read_text())
        out["g1_precision"] = g1.get("precision_auto_accept", g1.get("precision"))
    p = V2 / "genai" / "g2_narratives.json"
    if p.exists():
        recs = json.loads(p.read_text())
        n_llm = sum(1 for r in recs.values() if r.get("source") == "llm")
        out["g2_llm_narratives"] = n_llm
        out["g2_total_considered"] = len(recs)
    return out


def bundle(tee, args):
    """Freeze this run's artefacts into results/<run_id>/ — the local dump.

    _cache/v2 is a working directory that the next run overwrites. A submission
    needs a copy that cannot move under it, with hashes so it can be checked.
    """
    if not (V2 / "scores_v2_with_intervals.csv").exists():
        tee.write("bundle: no scores to copy — run build+validate first\n")
        return 1

    nums = headline_numbers()
    run_id = "%s_%s" % (nums["model_version"],
                        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    dest = RESULTS / run_id
    dest.mkdir(parents=True, exist_ok=True)

    manifest, n_bytes = [], 0
    for src in sorted(V2.rglob("*")):
        if src.is_dir() or src.name.startswith("."):
            continue
        rel = src.relative_to(V2)
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, target)
        manifest.append({"file": str(rel), "bytes": src.stat().st_size,
                         "sha256": sha256(src)})
        n_bytes += src.stat().st_size

    (dest / "MANIFEST.json").write_text(json.dumps(
        {"run_id": run_id, "bundled_at": datetime.now(timezone.utc).isoformat(),
         "headline": nums, "files": manifest}, indent=1, default=str))

    lines = ["# MAI v2 run — %s" % run_id, "",
             "Frozen copy of `analysis/audit/_cache/v2/`. Hashes in "
             "`MANIFEST.json`.", "",
             "| | |", "|---|---|"]
    for k in ("model_version", "created_at", "git_sha", "n_districts",
              "n_indicators", "imputed_pct", "top_district", "score_range",
              "g1_precision", "g2_llm_narratives"):
        if k in nums:
            lines.append("| %s | %s |" % (k.replace("_", " "), nums[k]))
    lines += ["| tests | %d of %d pass, %d fail |"
              % (nums["tests_pass"], nums["tests_total"], nums["tests_fail"]),
              "", "## Failing tests", ""]
    lines += ["- %s" % t for t in nums["failing_tests"]] or ["- none"]
    lines += ["", "Thresholds were fixed before the values existed; failures "
              "are reported, not tuned away."]
    (dest / "RESULTS.md").write_text("\n".join(lines) + "\n")

    latest = RESULTS / "latest"
    if latest.is_symlink() or latest.exists():
        latest.unlink() if latest.is_symlink() else shutil.rmtree(latest)
    try:
        latest.symlink_to(dest.name)
    except OSError:                                          # noqa: BLE001
        pass

    tee.write("bundled %d files (%.1f MB) -> %s\n"
              % (len(manifest), n_bytes / 1e6, dest))
    tee.write("  %d of %d tests pass · top district %s\n"
              % (nums["tests_pass"], nums["tests_total"], nums["top_district"]))
    return 0


# ------------------------------------------------------------------- driver
def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--confirm", action="store_true",
                    help="actually write to Firestore (default: dry run)")
    ap.add_argument("--pull", action="store_true",
                    help="refresh the local Firestore snapshot first")
    ap.add_argument("--skip-genai", action="store_true",
                    help="no Groq calls; narratives stay deterministic")
    ap.add_argument("--skip", default="",
                    help="comma-separated step names to skip")
    ap.add_argument("--only", default="",
                    help="comma-separated step names to run, in chain order")
    ap.add_argument("--from", dest="start", default=None,
                    help="resume: start at this step")
    ap.add_argument("--rpm", type=int, default=12,
                    help="Groq requests per minute (default 12; lower if rate-limited)")
    ap.add_argument("--g1-n", type=int, default=60,
                    help="labelled cases in the G1 evaluation")
    ap.add_argument("--g2-n", type=int, default=30,
                    help="pairs in the G2 blind judge")
    ap.add_argument("--list", action="store_true", help="show the steps and exit")
    args = ap.parse_args()

    chain = steps(args)
    if args.list:
        for name, cmd, fatal, desc in chain:
            print("  %-12s %-6s %s" % (name, "" if fatal else "(soft)", desc))
        return 0

    names = [s[0] for s in chain]
    skip = {s.strip() for s in args.skip.split(",") if s.strip()} | set(DEFAULT_SKIP)
    if args.pull:
        skip.discard("pull")
    if args.skip_genai:
        skip |= GENAI
    if args.only:
        keep = {s.strip() for s in args.only.split(",") if s.strip()}
        bad = keep - set(names)
        if bad:
            sys.exit("unknown step(s): %s\nknown: %s"
                     % (", ".join(sorted(bad)), ", ".join(names)))
        skip = set(names) - keep
    if args.start:
        if args.start not in names:
            sys.exit("unknown --from step: %s\nknown: %s"
                     % (args.start, ", ".join(names)))
        skip |= set(names[:names.index(args.start)])

    if not args.skip_genai and not (GENAI <= skip) and not have_groq():
        print("no GROQ key found — skipping the GenAI steps "
              "(narratives stay deterministic)")
        skip |= GENAI

    LOGS.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    tee = Tee(LOGS / ("run_all_%s.log" % stamp))
    t_all = time.time()
    results = []

    tee.write("MAI v2 full run — %s\n" % datetime.now().isoformat(timespec="seconds"))
    tee.write("firestore: %s\n" % ("WRITE (--confirm)" if args.confirm
                                   else "dry run"))
    tee.write("steps: %s\n" % ", ".join(n for n in names if n not in skip))

    for name, cmd, fatal, desc in chain:
        if name in skip:
            results.append((name, "skipped", 0.0))
            continue
        rule(tee, "=", "\n[%s]" % name)
        tee.write("%s\n" % desc)

        if name == "bundle":
            t0 = time.time()
            rc = bundle(tee, args)
            dt = time.time() - t0
        elif name == "publish":
            pub = [PY, "-m", "mai.publish"] + (["--confirm"] if args.confirm else [])
            rc, dt = run(pub, tee)
        else:
            rc, dt = run(cmd, tee)

        if rc == 0:
            results.append((name, "ok", dt))
        elif fatal:
            results.append((name, "FAILED", dt))
            break
        else:
            results.append((name, "soft-fail", dt))
            tee.write("\n! %s failed (rc=%d) — continuing; this step is "
                      "optional by design.\n" % (name, rc))

    rule(tee, "=", "\n[summary]")
    for name, status, dt in results:
        tee.write("  %-12s %-10s %6.1fs\n" % (name, status, dt))
    tee.write("  %-12s %-10s %6.1fs\n"
              % ("TOTAL", "", time.time() - t_all))
    failed = [n for n, s, _ in results if s == "FAILED"]
    if failed:
        tee.write("\nSTOPPED at %s. Fix it, then: python3 run_all.py --from %s\n"
                  % (failed[0], failed[0]))
    elif not args.confirm and "publish" not in skip:
        tee.write("\nNothing was written to Firestore. Re-run with --confirm "
                  "to publish 698 mai_scores + 1 mai_runs.\n")
    tee.write("log: %s\n" % (LOGS / ("run_all_%s.log" % stamp)))
    tee.close()
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
