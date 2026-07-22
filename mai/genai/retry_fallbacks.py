"""Re-run ONLY the districts where the LLM layer fell back, for BOTH G1 and G2.

A full G1/G2 pass is expensive and most of it already succeeded. This script
reads the v2 archives, finds the rows that did NOT get an LLM result, feeds just
those back to the model, and writes the successes into the same files — leaving
every row that already passed untouched.

What counts as "fell back"
  G1  analysis/audit/_cache/v2/genai/g1_resolutions.csv
      rows whose `agreement` is "api_error" — the LLM never produced a verdict
      for that label because the call itself failed.
  G2  analysis/audit/_cache/v2/genai/g2_narratives.json
      entries whose `source` is not "llm" — either the API failed
      (`template_api_error`) or the draft stated a number it was not given and
      the numeric verifier rejected it (`template_fallback`). Both are re-fed;
      the verifier still guards every new draft, so fidelity is not relaxed.

Key rotation (the .env contract)
  Put several keys in .env as a comma-separated GROQ_API_KEYS (numbered
  GROQ_API_KEY_2.. and Credentials/Groq.json are also picked up). For every
  call the policy is:

      key1 -> key2 -> … -> keyN  -> key1 again  -> the role's fallback model

  i.e. try each key in turn; if the last one fails, give the FIRST key one more
  attempt; only then move to the declared alternate model and run the same key
  cycle again. Every hop is logged. A key that returns a per-DAY limit is
  remembered and skipped for the rest of the run.

    python3 -m mai.genai.retry_fallbacks              # both G1 and G2
    python3 -m mai.genai.retry_fallbacks --g2         # only G2
    python3 -m mai.genai.retry_fallbacks --dry-run    # list, call nothing

Read-only with respect to Firestore. Publishing stays a separate, explicit step
(`python3 -m mai.publish --confirm`), which already prefers an LLM narrative
over a template wherever one now exists.
"""
import argparse
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from mai import data as D                                   # noqa: E402
from mai import narrative as tmpl                           # noqa: E402
from mai.genai import g1_crosswalk as g1                    # noqa: E402
from mai.genai import g2_narrative as g2                    # noqa: E402
from mai.genai.client import (GroqClient, ROLE_FALLBACKS,   # noqa: E402
                              model_for)

OUT = D.CACHE / "v2" / "genai"


class _DailyExhausted(Exception):
    """A key hit its per-day allowance on a given model."""

    def __init__(self, role, model):
        self.role, self.model = role, model


class RotatingGroqClient(GroqClient):
    """GroqClient with the .env key-rotation contract this script promises.

    The base client already parses every key and, on a per-day 429, rotates
    key-then-model. This subclass makes the rotation policy explicit and applies
    it to EVERY failure (rate limit, transport, daily cap): each key in turn,
    the first key once more, then the declared fallback model — with each hop
    recorded. Re-entrant internal retries inside the base call (schema
    downgrade, token-budget growth) run without rotation, as they should.
    """

    def __init__(self, per_minute=12, **kw):
        super().__init__(per_minute=per_minute, max_retries=2, **kw)
        self._inside = False
        self.dead = set()               # (key_index, model) daily-exhausted this run
        self.rotation_log = []

    def _log(self, msg):
        self.rotation_log.append(msg)
        print("      [rotate] " + msg)

    def _on_daily_exhaustion(self, role, model):
        # base calls this on a per-DAY 429; don't self-rotate — signal upward so
        # _rotate owns the whole policy in one place.
        self.dead.add((self.key_index, model))
        raise _DailyExhausted(role, model)

    # Signature MUST match GroqClient.chat exactly: the base implementation
    # recurses positionally (schema downgrade, token-budget growth), and those
    # inner calls land back here.
    def chat(self, role, system, user, temperature=0.0, json_schema=None,
             max_tokens=1024, reasoning_effort=None):
        args = (temperature, json_schema, max_tokens, reasoning_effort)
        if self._inside:                       # internal base retry: no rotation
            return GroqClient.chat(self, role, system, user, *args)
        self._inside = True
        try:
            return self._rotate(role, system, user, *args)
        finally:
            self._inside = False

    def _rotate(self, role, system, user, *args):
        base = model_for(role)
        models = [base] + [m for m in ROLE_FALLBACKS.get(role, []) if m != base]
        n = len(self.keys)
        # each key once, then the FIRST key one more time (only meaningful n>1)
        key_order = list(range(n)) + ([0] if n > 1 else [])
        last = None
        for mi, model in enumerate(models):
            self.substitutions.pop(role, None) if model == base \
                else self.substitutions.__setitem__(role, model)
            for pos, k in enumerate(key_order):
                if (k, model) in self.dead:
                    continue
                self._use_key(k)
                recheck = " (first-key recheck)" if pos == n else ""
                try:
                    out = GroqClient.chat(self, role, system, user, *args)
                    if k != 0 or mi > 0:
                        self._log("%s ok on key #%d / %s%s"
                                  % (role, k + 1, model, recheck))
                    return out
                except _DailyExhausted:
                    last = "daily cap"
                    self._log("%s key #%d daily-capped on %s — next key"
                              % (role, k + 1, model))
                except RuntimeError as e:
                    last = str(e)[:90]
                    self._log("%s key #%d failed on %s%s — next: %s"
                              % (role, k + 1, model, recheck, last))
            if mi + 1 < len(models):
                self._log("%s: keys exhausted on %s -> fallback model %s"
                          % (role, model, models[mi + 1]))
        self.substitutions.pop(role, None)
        raise RuntimeError("all %d key(s) and %d model(s) exhausted for %s (last: %s)"
                           % (n, len(models), role, last))


def _backup(path):
    if path.exists():
        b = path.with_suffix(path.suffix + ".pre_retry_"
                             + datetime.now().strftime("%Y%m%d_%H%M%S") + ".bak")
        shutil.copy2(path, b)
        print("  backup -> %s" % b.name)


# ------------------------------------------------------------------ G2 narratives
def retry_g2(client, dry_run=False, limit=None):
    path = OUT / "g2_narratives.json"
    if not path.exists():
        print("G2: no g2_narratives.json — run g2_narrative --generate first. Skipping.")
        return
    recs = json.load(open(path))
    todo = [c for c, v in recs.items() if v.get("source") != "llm"]
    from collections import Counter
    breakdown = Counter(recs[c].get("source") for c in todo)
    print("\n=== G2 — %d of %d narratives fell back %s"
          % (len(todo), len(recs), dict(breakdown)))
    if not todo:
        print("  nothing to retry.")
        return
    if limit:
        todo = todo[:limit]
    if dry_run:
        for c in todo:
            print("  would retry %s (%s)" % (c, recs[c].get("source")))
        return

    scores = pd.read_csv(D.CACHE / "v2" / "scores_v2_with_intervals.csv",
                         index_col=0)
    pillars = [c for c in scores.columns
               if c.startswith(("P2_", "P3_", "P4_", "P5_"))]
    total = len(scores)
    client.validate_roles(["G2_GENERATE"])

    fixed = still = errored = 0
    for i, code in enumerate(todo, 1):
        key = int(code) if int(code) in scores.index else code
        row = scores.loc[key]
        print("  [%d/%d] %s — %s" % (i, len(todo), code, row["district_name"]))
        try:
            text, ok, bad, facts = g2.generate_one(client, row, pillars, total)
        except RuntimeError as e:
            errored += 1
            recs[code] = {**recs[code], "source": "template_api_error",
                          "error": str(e)[:200]}
            print("     still failing after rotation: %s" % str(e)[:90])
            continue
        if ok:
            fixed += 1
            recs[code] = {"narrative": text, "source": "llm",
                          "model": client.model_for_role("G2_GENERATE"),
                          "recovered_by": "retry_fallbacks"}
            print("     recovered -> llm (%s)" % client.model_for_role("G2_GENERATE"))
        else:
            still += 1
            fallback, _ = tmpl.narrative(row, pillars, total)
            recs[code] = {"narrative": fallback, "source": "template_fallback",
                          "rejected_numbers": bad, "llm_draft": text}
            print("     draft still failed numeric check on %s — kept template" % bad)

    _backup(path)
    json.dump(recs, open(path, "w"), indent=1)
    n_llm = sum(1 for v in recs.values() if v.get("source") == "llm")
    print("  G2 result: recovered %d · still-rejected %d · still-errored %d"
          % (fixed, still, errored))
    print("  G2 narratives now llm: %d / %d" % (n_llm, len(recs)))


# ------------------------------------------------------------------- G1 crosswalk
def retry_g1(client, dry_run=False, limit=None):
    path = OUT / "g1_resolutions.csv"
    if not path.exists():
        print("G1: no g1_resolutions.csv — run g1_crosswalk --resolve first. Skipping.")
        return
    df = pd.read_csv(path)
    mask = df["agreement"] == "api_error"
    todo = df[mask]
    print("\n=== G1 — %d of %d resolutions failed with an api_error"
          % (len(todo), len(df)))
    if todo.empty:
        print("  nothing to retry.")
        return
    if limit:
        todo = todo.head(limit)
    if dry_run:
        for r in todo.itertuples():
            print("  would retry %s / %s (%s)" % (r.state, r.label, r.source))
        return

    ind = D.load("district_indicators")
    pca, _ = D.load_pca_repaired()
    dim = D.build_spine(ind, pca)
    nbs = D.spine_names_by_state(dim)
    client.validate_roles(["G1_PROPOSE", "G1_VERIFY", "G1_TIEBREAK"])

    fixed = still = 0
    for i, r in enumerate(todo.itertuples(), 1):
        cands = g1._candidates(nbs, r.source_state if hasattr(r, "source_state")
                               else r.state)
        state = r.state
        print("  [%d/%d] %s / %s" % (i, len(todo), state, r.label))
        if not cands:
            print("     no candidate spine districts for %s — cannot resolve" % state)
            continue
        try:
            rec = g1.resolve_one(client, state, str(r.label), r.source, cands,
                                 national=nbs)
        except RuntimeError as e:
            print("     still failing after rotation: %s" % str(e)[:90])
            df.loc[r.Index, "reasoning"] = str(e)[:200]
            continue
        for col in ("decision", "target", "agreement", "confidence",
                    "propose_target", "verify_target", "tiebreak_target",
                    "propose_category", "verify_category", "reasoning"):
            if col in df.columns and col in rec:
                df.loc[r.Index, col] = rec[col]
        if rec["agreement"] == "api_error":
            still += 1
            print("     still api_error")
        else:
            fixed += 1
            print("     resolved -> %s (%s, %s)"
                  % (rec.get("target"), rec["decision"], rec["agreement"]))

    _backup(path)
    df.to_csv(path, index=False)
    n_err = int((df["agreement"] == "api_error").sum())
    n_acc = int(df["decision"].isin(["ACCEPT", "ACCEPT_MAJORITY"]).sum())
    print("  G1 result: resolved %d · still-errored %d" % (fixed, still))
    print("  G1 rows now: %d accepted · %d api_error remaining" % (n_acc, n_err))


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--g1", action="store_true", help="retry G1 only")
    ap.add_argument("--g2", action="store_true", help="retry G2 only")
    ap.add_argument("--rpm", type=int, default=12,
                    help="requests per minute (default 12)")
    ap.add_argument("--limit", type=int, default=None,
                    help="cap the number of rows retried, per layer")
    ap.add_argument("--dry-run", action="store_true",
                    help="list the fallback rows and exit without calling Groq")
    args = ap.parse_args()
    do_g1 = args.g1 or not (args.g1 or args.g2)
    do_g2 = args.g2 or not (args.g1 or args.g2)

    client = None
    if not args.dry_run:
        client = RotatingGroqClient(per_minute=args.rpm)
        print("keys available: %d  ·  rotation: key1..keyN, then key1 again, "
              "then the fallback model" % len(client.keys))

    if do_g1:
        retry_g1(client, dry_run=args.dry_run, limit=args.limit)
    if do_g2:
        retry_g2(client, dry_run=args.dry_run, limit=args.limit)

    if client is not None:
        print("\ngroq usage:", client.stats())
        if client.substitutions:
            print("model substitutions in effect:", dict(client.substitutions))


if __name__ == "__main__":
    main()
