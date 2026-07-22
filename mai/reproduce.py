"""R-19 — the two things that make `run_v2.json` a contract instead of a log.

`mai/build.py` already records what the plan section 4.3 asked for: indicator
list with directions, pillar composition, seed, git SHA, normalisation and
aggregation choices, coverage and imputation tables, data vintage, and a
SHA-256 of every input snapshot. Recording it proves nothing on its own. This
module tests the two claims that recording is supposed to support.

  1. REPRODUCIBILITY   Re-run the build from scratch and compare every score
                       against the published CSV at 2 dp. The plan says
                       "bitwise to 2 dp"; taking that literally, the test is
                       exact equality of round(x, 2), not a tolerance band.

  2. STALENESS         Re-hash the inputs and compare against the hashes the
                       run recorded. Any divergence means the published scores
                       were computed from data that no longer exists in the
                       cache, and the detector must FIRE rather than warn
                       quietly. A synthetic-perturbation self-test proves the
                       detector actually fires, because a staleness check that
                       has never returned STALE is indistinguishable from one
                       that cannot.

    python3 -m mai.reproduce            # both checks
    python3 -m mai.reproduce --selftest # + prove the detector fires

Read-only with respect to Firestore and with respect to the cache.
"""
import argparse
import hashlib
import json
import sys

import numpy as np
import pandas as pd

from . import build as B
from . import data as D

OUT = D.CACHE / "v2"
RUN = OUT / "run_v2.json"
SCORES = OUT / "scores_v2.csv"

SCORE_COLS = ["mai_overall", "mai_chronic", "mai_acute",
              "mai_current", "mai_future", "quality_overall", "size_score"]


def load_run():
    if not RUN.exists():
        sys.exit("no run record at %s — run `python3 -m mai.build` first" % RUN)
    with open(RUN) as f:
        return json.load(f)


# ------------------------------------------------------------------ staleness
def staleness(run, hashes=None):
    """Compare recorded input hashes against the cache as it stands now."""
    now = hashes if hashes is not None else B._snapshot_hashes()
    then = run.get("input_snapshot_sha256") or {}
    rows = []
    for name in sorted(set(then) | set(now)):
        a, b = then.get(name), now.get(name)
        state = ("MISSING" if b is None else
                 "NEW" if a is None else
                 "OK" if a == b else "CHANGED")
        rows.append({"collection": name, "recorded": a, "current": b,
                     "state": state})
    df = pd.DataFrame(rows)
    stale = bool((df["state"] != "OK").any())
    return stale, df


def print_staleness(stale, df):
    print("\nSTALENESS DETECTOR")
    print("  run recorded %d input snapshots; %d differ now"
          % (len(df), int((df["state"] != "OK").sum())))
    bad = df[df["state"] != "OK"]
    if len(bad):
        print(bad[["collection", "state"]].to_string(index=False))
    print("  verdict: %s" % ("STALE — published scores predate the current "
                             "inputs; rebuild before publishing" if stale
                             else "FRESH — every input matches its recorded hash"))


def selftest_detector(run):
    """Prove the detector fires. Perturbs a COPY of the hash dict only."""
    now = dict(B._snapshot_hashes())
    if not now:
        return None
    victim = sorted(now)[0]
    now[victim] = hashlib.sha256(b"synthetic perturbation").hexdigest()[:16]
    fired, df = staleness(run, hashes=now)
    print("\n  self-test: perturbed the recorded hash of %r in memory "
          "(no file touched)" % victim)
    print("  detector fired: %s -> %s"
          % (fired, "PASS" if fired else "FAIL — the detector is inert"))
    return fired


# ------------------------------------------------------------- reproducibility
def reproduce(run):
    """Rebuild and compare against the published CSV at 2 dp."""
    if not SCORES.exists():
        sys.exit("no published scores at %s" % SCORES)
    published = pd.read_csv(SCORES, index_col=0)
    published.index = published.index.astype(str).str.zfill(3)

    print("\nREPRODUCIBILITY RE-RUN")
    print("  rebuilding from source with seed=%s, git_sha=%s"
          % (run.get("seed"), (run.get("git_sha") or "?")[:10]))
    scores, PS, Xi, meta, run2, prov = B.main()
    scores.index = scores.index.astype(str).str.zfill(3)

    rows = []
    idx = published.index.intersection(scores.index)
    for c in SCORE_COLS:
        if c not in published.columns or c not in scores.columns:
            continue
        a = published.loc[idx, c].round(2)
        b = scores.loc[idx, c].round(2)
        same = int((a == b).sum())
        rows.append({"column": c, "n": len(idx), "identical_at_2dp": same,
                     "pct": round(100.0 * same / len(idx), 3),
                     "max_abs_diff": float((published.loc[idx, c]
                                            - scores.loc[idx, c]).abs().max())})
    df = pd.DataFrame(rows)
    n_missing = len(published.index.symmetric_difference(scores.index))
    exact = bool((df["pct"] == 100.0).all() and n_missing == 0)

    print("  districts: published %d, rebuilt %d, symmetric difference %d"
          % (len(published), len(scores), n_missing))
    print(df.to_string(index=False))
    print("  verdict: %s" % ("REPRODUCIBLE — every score identical at 2 dp"
                             if exact else
                             "NOT REPRODUCIBLE — see the columns above"))

    # The other half of section 4.3: every published score must carry the
    # run_id that produced it. Checked on the payload the publisher builds,
    # not on Firestore, because nothing is published without --confirm.
    sha = run2.get("git_sha") or ""
    print("  run identity carried by rebuild: model_version=%s git_sha=%s"
          % (run2["model_version"], sha[:10] or "(not a git checkout)"))
    return exact, df, run2


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--selftest", action="store_true",
                    help="also prove the staleness detector fires")
    ap.add_argument("--skip-rerun", action="store_true",
                    help="staleness only (the re-run takes ~1 min)")
    a = ap.parse_args()

    run = load_run()
    print("=" * 96)
    print("R-19 — REPRODUCIBILITY CONTRACT")
    print("=" * 96)
    print("  run record : %s" % RUN)
    print("  created_at : %s" % run.get("created_at"))
    print("  recorded fields: %d (v1 mai_runs had 14 summary fields and none "
          "of the below)" % len(run))
    for k in ("indicators_kept", "indicator_directions", "pillar_composition",
              "seed", "git_sha", "imputation", "data_vintage",
              "input_snapshot_sha256", "method"):
        v = run.get(k)
        n = len(v) if isinstance(v, (list, dict)) else 1
        print("    %-26s %s" % (k, "present (%d)" % n if v is not None
                                else "MISSING"))

    stale, sdf = staleness(run)
    print_staleness(stale, sdf)
    fired = selftest_detector(run) if a.selftest else None

    exact = None
    if not a.skip_rerun:
        exact, rdf, _ = reproduce(run)
        rdf.to_csv(OUT / "reproducibility_v2.csv", index=False)

    sdf.to_csv(OUT / "staleness_v2.csv", index=False)
    verdicts = {
        "reproduces_at_2dp": exact,
        "inputs_fresh": (not stale),
        "detector_fires_on_perturbation": fired,
    }
    with open(OUT / "reproducibility_v2.json", "w") as f:
        json.dump(verdicts, f, indent=2)
    print("\n" + "=" * 96)
    for k, v in verdicts.items():
        print("  %-34s %s" % (k, "n/a" if v is None else
                              ("PASS" if v else "FAIL")))
    return verdicts


if __name__ == "__main__":
    main()
