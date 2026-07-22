"""G1 — LLM-assisted district crosswalk resolution (roadmap R-11).

The problem, restated from audit C-05: Ni-kshay, PMJAY and the NFHS-5 factsheet
label districts in ways no edit-distance metric can resolve. `dharashiv` IS
Osmanabad. `chhatrapati sambhajinagar` IS Aurangabad. `ntr` is a 2022 district
carved from Krishna. `mumbai colaba` is a TB reporting unit, not a district.
String similarity between each of those pairs is near zero.

Design — the parts that make this a defensible method rather than a chatbot:

  CLOSED VOCABULARY.  The model never generates a district name. It is handed
  the exact list of spine districts for the state and must return one of them
  verbatim, or null. Anything not in the list is rejected by code before it can
  reach the crosswalk.

  TWO FAMILIES MUST AGREE.  `llama-3.3-70b-versatile` proposes;
  `openai/gpt-oss-120b` independently resolves the same label with no sight of
  the first answer. Agreement is required to auto-accept. Two runs of ONE model
  at temperature 0 agree with themselves by construction and prove nothing —
  the plan's "two independent runs must agree" is only meaningful across
  families. `qwen/qwen3.6-27b` breaks ties as a third family; a 2-of-3 majority
  is accepted at reduced confidence, everything else queues for review.

  PARENT CITATION REQUIRED.  Any SPLIT_CHILD mapping must name the parent
  district and the reorganisation year, which is a checkable claim.

  EVALUATION AGAINST HELD-OUT TRUTH.  The deterministic alias table built in
  R-04 is reviewed ground truth. `--eval` hides its answers and scores the LLM
  against them: precision on auto-accepted mappings is the bar (>= 0.95),
  because a wrong merge corrupts two districts at once.

    python3 -m mai.genai.g1_crosswalk --eval          # score against R-04 truth
    python3 -m mai.genai.g1_crosswalk --resolve       # resolve open items
"""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from mai import crosswalk as xw          # noqa: E402
from mai import data as D                # noqa: E402
from mai.genai.client import GroqClient, model_for   # noqa: E402

OUT = D.CACHE / "v2" / "genai"

CATEGORIES = ["EXACT", "RENAME", "SPLIT_CHILD", "SUBUNIT", "CROSS_STATE",
              "NOT_A_DISTRICT", "UNKNOWN"]

SCHEMA = {
    "type": "object",
    "properties": {
        "target": {"type": ["string", "null"]},
        "category": {"type": "string", "enum": CATEGORIES},
        "confidence": {"type": "number"},
        "parent_or_former_name": {"type": ["string", "null"]},
        "year": {"type": ["integer", "null"]},
        "reasoning": {"type": "string"},
    },
    "required": ["target", "category", "confidence",
                 "parent_or_former_name", "year", "reasoning"],
    "additionalProperties": False,
}

SYSTEM = """You are an expert on Indian administrative geography: district \
creation, renaming and reorganisation from the 2011 Census to today, and the \
sub-district reporting units used by health programmes (Ni-kshay TB units, \
PMJAY empanelment districts, municipal corporations, chest clinics).

You will be given ONE source label from a health dataset, its state, and the \
COMPLETE list of district names available in our 2011/2017-vintage spine for \
that state.

Return the single spine district that the source label's population belongs to.

HARD RULES
1. `target` MUST be copied verbatim from the candidate list, or be null. Never \
invent, translate or reformat a name.
2. If the label is a district created after the spine vintage, map it to the \
PARENT district it was carved from, set category SPLIT_CHILD, and give the \
parent's former name and the creation year.
3. If the label is a renamed district, map to the spine's name for the same \
territory, category RENAME (e.g. Dharashiv -> Osmanabad, Chhatrapati \
Sambhajinagar -> Aurangabad, Gurugram -> Gurgaon).
4. If the label is a sub-district reporting unit (a city ward, a chest clinic, \
a municipal corporation, "X Rural"), map it to its parent district, category \
SUBUNIT.
5. If it is not a district at all (a ministry, a PSU pool, a state aggregate), \
target null, category NOT_A_DISTRICT.
6. If you are not confident, target null, category UNKNOWN. A wrong merge \
corrupts two districts at once, so silence is strongly preferred to a guess.
7. `confidence` is 0.0-1.0 and must reflect genuine uncertainty."""

USER_TMPL = """State: {state}
Source label: "{label}"
Source dataset: {source}

Candidate spine districts for this state (choose EXACTLY one, verbatim, or null):
{candidates}

Which spine district does this label's population belong to?"""


def _ask(client, role, state, label, source, candidates):
    return client.chat(
        role, SYSTEM,
        USER_TMPL.format(state=state, label=label, source=source,
                         candidates="\n".join("  - " + c for c in candidates)),
        # Groq bills the REQUESTED completion budget against the per-model
        # TPM ceiling, so an oversized budget throttles the run rather than
        # protecting it. 900 tokens plus low reasoning effort fits a single
        # closed-vocabulary pick comfortably.
        temperature=0.0, json_schema=SCHEMA, max_tokens=900,
        reasoning_effort="low")


def _norm_target(ans, candidates):
    """Reject anything outside the closed vocabulary."""
    t = ans.get("target")
    if t is None:
        return None
    t = xw.norm_name(t)
    return t if t in candidates else "__OFF_VOCAB__"


def resolve_one(client, state, label, source, candidates, national=None):
    """Two families independently; a third only on disagreement.

    `national` is an optional {state: [districts]} map used for a second pass
    when both families answer null. Sources misfile districts across states —
    PMJAY lists Telangana districts under Andhra Pradesh — and a state-scoped
    candidate list makes those unanswerable by construction. Rather than record
    a false negative, re-ask against the neighbouring states.
    """
    a = _ask(client, "G1_PROPOSE", state, label, source, candidates)
    b = _ask(client, "G1_VERIFY", state, label, source, candidates)
    ta, tb = _norm_target(a, candidates), _norm_target(b, candidates)

    if ta is None and tb is None and national:
        cross = _cross_state_pass(client, state, label, source, national)
        if cross:
            return cross

    rec = {
        "state": state, "label": label, "source": source,
        "propose_model": model_for("G1_PROPOSE"),
        "verify_model": model_for("G1_VERIFY"),
        "propose_target": ta, "verify_target": tb,
        "propose_category": a.get("category"), "verify_category": b.get("category"),
        "propose_conf": a.get("confidence"), "verify_conf": b.get("confidence"),
        "parent": a.get("parent_or_former_name"), "year": a.get("year"),
        "reasoning": (a.get("reasoning") or "")[:400],
        "tiebreak_target": None, "tiebreak_model": None,
    }

    if "__OFF_VOCAB__" in (ta, tb):
        rec.update(decision="REVIEW", target=None, agreement="off_vocabulary",
                   confidence=0.0)
        return rec

    if ta == tb:
        conf = min(a.get("confidence", 0), b.get("confidence", 0))
        rec.update(decision=("ACCEPT" if ta is not None else "NOT_A_DISTRICT"),
                   target=ta, agreement="both_families", confidence=conf)
        return rec

    c = _ask(client, "G1_TIEBREAK", state, label, source, candidates)
    tc = _norm_target(c, candidates)
    rec["tiebreak_target"] = tc
    rec["tiebreak_model"] = model_for("G1_TIEBREAK")
    votes = Counter([t for t in (ta, tb, tc) if t != "__OFF_VOCAB__"])
    top, n = (votes.most_common(1) or [(None, 0)])[0]
    if n >= 2:
        rec.update(decision="ACCEPT_MAJORITY", target=top,
                   agreement="2_of_3", confidence=0.6)
    else:
        rec.update(decision="REVIEW", target=None, agreement="no_majority",
                   confidence=0.0)
    return rec


def _candidates(names_by_state, state):
    return sorted(names_by_state.get(xw.norm_state(state), set()))


CROSS_SYSTEM = SYSTEM + """

CROSS-STATE PASS: the source dataset may have filed this district under the
wrong state. You are now given districts from OTHER states. Return the state
and district it actually belongs to, or null if none fit."""

CROSS_SCHEMA = {
    "type": "object",
    "properties": {
        "state": {"type": ["string", "null"]},
        "target": {"type": ["string", "null"]},
        "confidence": {"type": "number"},
        "reasoning": {"type": "string"},
    },
    "required": ["state", "target", "confidence", "reasoning"],
    "additionalProperties": False,
}


def _cross_state_pass(client, state, label, source, national):
    """Ask both families whether the label belongs to a different state."""
    listing = "\n".join(
        "  %s: %s" % (st, ", ".join(sorted(ds)))
        for st, ds in sorted(national.items()) if st != xw.norm_state(state))
    user = ('Source label: "%s" (filed under state: %s, dataset: %s)\n\n'
            "Districts by state:\n%s\n\nWhich state and district is this?"
            % (label, state, source, listing))
    outs = []
    for role in ("G1_PROPOSE", "G1_VERIFY"):
        try:
            r = client.chat(role, CROSS_SYSTEM, user, temperature=0.0,
                            json_schema=CROSS_SCHEMA, max_tokens=900,
                            reasoning_effort="low")
        except RuntimeError:
            return None
        st = xw.norm_state(r.get("state") or "")
        tgt = xw.norm_name(r.get("target") or "") if r.get("target") else None
        outs.append((st, tgt) if tgt and tgt in national.get(st, set()) else (None, None))
    if outs[0] == outs[1] and outs[0][1] is not None:
        return {"state": state, "label": label, "source": source,
                "propose_model": model_for("G1_PROPOSE"),
                "verify_model": model_for("G1_VERIFY"),
                "propose_target": outs[0][1], "verify_target": outs[1][1],
                "propose_category": "CROSS_STATE", "verify_category": "CROSS_STATE",
                "propose_conf": None, "verify_conf": None,
                "parent": None, "year": None,
                "reasoning": "cross-state pass: filed under %s, belongs to %s"
                             % (state, outs[0][0]),
                "tiebreak_target": None, "tiebreak_model": None,
                "decision": "ACCEPT", "target": outs[0][1],
                "agreement": "both_families_cross_state",
                "confidence": 0.8, "resolved_state": outs[0][0]}
    return None


def build_truth():
    """Ground truth from the reviewed R-04 alias table.

    Only 1:1 mappings are usable as a precision test — PRORATE entries are
    deliberately many-target and DROP entries have no target.
    """
    rows = []
    for (state, label), (cat, targets) in xw.ALIASES.items():
        if cat in (xw.PRORATE, xw.DROP) or len(targets) != 1:
            continue
        rows.append({"state": state, "label": label,
                     "truth": targets[0], "truth_category": cat})
    return pd.DataFrame(rows)


def run_eval(client, n=60, seed=42):
    ind = D.load("district_indicators")
    pca, _ = D.load_pca_repaired()
    dim = D.build_spine(ind, pca)
    nbs = D.spine_names_by_state(dim)

    truth = build_truth()
    truth = truth[truth["state"].isin(nbs)]
    truth = truth.sample(min(n, len(truth)), random_state=seed)
    print("G1 EVALUATION — %d held-out mappings from the reviewed R-04 table"
          % len(truth))
    print("  propose=%s  verify=%s  tiebreak=%s\n"
          % (model_for("G1_PROPOSE"), model_for("G1_VERIFY"),
             model_for("G1_TIEBREAK")))

    recs = []
    for i, r in enumerate(truth.itertuples(), 1):
        cands = _candidates(nbs, r.state)
        rec = resolve_one(client, r.state, r.label, "eval", cands, national=nbs)
        rec["truth"] = r.truth
        rec["truth_category"] = r.truth_category
        rec["correct"] = (rec["target"] == r.truth)
        recs.append(rec)
        if i % 10 == 0:
            print("    %d/%d …" % (i, len(truth)))
    df = pd.DataFrame(recs)

    auto = df[df["decision"].isin(["ACCEPT", "ACCEPT_MAJORITY"])]
    prec = auto["correct"].mean() if len(auto) else float("nan")
    recall = df["correct"].mean()
    both = df[df["agreement"] == "both_families"]
    print("\n  auto-accepted            : %d / %d (%.1f%%)"
          % (len(auto), len(df), 100 * len(auto) / len(df)))
    print("  PRECISION on auto-accept : %.3f   (bar >= 0.95)  -> %s"
          % (prec, "PASS" if prec >= 0.95 else "FAIL"))
    print("  recall over all items    : %.3f" % recall)
    print("  queued for human review  : %d (the cost of that precision)"
          % int((df["decision"] == "REVIEW").sum()))
    print("  two-family agreement rate: %.1f%%" % (100 * len(both) / len(df)))
    if len(both):
        print("  precision when families agree: %.3f" % both["correct"].mean())
    bad = df[df["decision"].isin(["ACCEPT", "ACCEPT_MAJORITY"]) & ~df["correct"]]
    if len(bad):
        print("\n  WRONG auto-accepts (these are what the bar exists to catch):")
        print(bad[["state", "label", "target", "truth", "agreement"]]
              .to_string(index=False))

    OUT.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT / "g1_eval.csv", index=False)
    summary = {
        "n": int(len(df)), "auto_accepted": int(len(auto)),
        "precision_auto_accept": None if pd.isna(prec) else round(float(prec), 4),
        "recall_all": round(float(recall), 4),
        "review_queue": int((df["decision"] == "REVIEW").sum()),
        "two_family_agreement_rate": round(100 * len(both) / len(df), 1),
        "models": {"propose": model_for("G1_PROPOSE"),
                   "verify": model_for("G1_VERIFY"),
                   "tiebreak": model_for("G1_TIEBREAK")},
        "bar": "precision >= 0.95 on auto-accepted mappings",
        "verdict": "PASS" if (not pd.isna(prec) and prec >= 0.95) else "FAIL",
        "groq_usage": client.stats(),
    }
    with open(OUT / "g1_eval_summary.json", "w") as f:
        json.dump(summary, f, indent=2)
    return df, summary


def run_resolve(client, limit=None):
    """Resolve the labels the deterministic table still leaves open."""
    review = D.CACHE / "v2" / "crosswalk_review_v2.csv"
    if not review.exists():
        sys.exit("run `python3 -m mai.build` first")
    df = pd.read_csv(review)
    open_items = df[df["category"].isin(["UNRESOLVED", "FUZZY", "SUFFIX+FUZZY"])]
    open_items = open_items.drop_duplicates(["source_state", "label"])
    if limit:
        open_items = open_items.head(limit)

    ind = D.load("district_indicators")
    pca, _ = D.load_pca_repaired()
    dim = D.build_spine(ind, pca)
    nbs = D.spine_names_by_state(dim)

    print("G1 RESOLVE — %d open labels (UNRESOLVED + FUZZY)" % len(open_items))
    recs = []
    for i, r in enumerate(open_items.itertuples(), 1):
        cands = _candidates(nbs, r.source_state)
        if not cands:
            continue
        try:
            rec = resolve_one(client, r.source_state, str(r.label),
                              getattr(r, "source", "unknown"), cands,
                              national=nbs)
        except RuntimeError as e:
            # A rate-limit or transport failure on one label must not discard
            # the whole run — record it as a review item and continue.
            rec = {"state": r.source_state, "label": r.label,
                   "source": getattr(r, "source", "unknown"),
                   "decision": "REVIEW", "target": None,
                   "agreement": "api_error", "confidence": 0.0,
                   "reasoning": str(e)[:200]}
        rec["deterministic_category"] = r.category
        rec["deterministic_target"] = getattr(r, "targets", None)
        recs.append(rec)
        if i % 10 == 0:
            print("    %d/%d …" % (i, len(open_items)))
    out = pd.DataFrame(recs)
    OUT.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT / "g1_resolutions.csv", index=False)

    acc = out[out["decision"].isin(["ACCEPT", "ACCEPT_MAJORITY"])]
    print("\n  auto-accepted : %d" % len(acc))
    print("  not a district: %d" % int((out["decision"] == "NOT_A_DISTRICT").sum()))
    print("  review queue  : %d" % int((out["decision"] == "REVIEW").sum()))
    print("  where the LLM DISAGREES with the deterministic fuzzy match:")
    dis = acc[acc["deterministic_category"].isin(["FUZZY", "SUFFIX+FUZZY"])]
    dis = dis[dis["target"] != dis["deterministic_target"]]
    print(dis[["state", "label", "deterministic_target", "target"]]
          .to_string(index=False) if len(dis) else "    (none)")
    print("\n  written -> %s" % (OUT / "g1_resolutions.csv"))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--eval", action="store_true")
    ap.add_argument("--resolve", action="store_true")
    ap.add_argument("--n", type=int, default=60)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--rpm", type=int, default=25)
    args = ap.parse_args()

    client = GroqClient(per_minute=args.rpm)
    client.validate_roles(["G1_PROPOSE", "G1_VERIFY", "G1_TIEBREAK"])
    if args.eval:
        run_eval(client, n=args.n)
    if args.resolve:
        run_resolve(client, limit=args.limit)
    if not (args.eval or args.resolve):
        ap.print_help()
    print("\ngroq usage:", client.stats())


if __name__ == "__main__":
    main()
