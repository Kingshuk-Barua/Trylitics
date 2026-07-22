"""G2 — LLM district narratives grounded in the pillar decomposition (R-14).

`mai/narrative.py` already produces a deterministic template brief with a hard
numeric-fidelity guarantee. This module is the LLM layer that sits ON TOP of
that, never instead of it — the plan's evaluation demands 100% numeric fidelity
with zero tolerance, which is only achievable if the numbers are placed by code
and the model is confined to prose and judgement.

Two model families, and the split is the whole point of the eval:

    GENERATE  openai/gpt-oss-20b       698 districts, fastest text model
    JUDGE     llama-3.3-70b-versatile  blind-rates actionability

A model must never blind-rate its own output, so the judge is a different
family from the generator. The judge scores the LLM narrative and the
deterministic template side by side, shuffled and unlabelled, and the question
is whether the LLM actually beats string formatting — which is the plan's
stated bar (mean >= 4.0 on a 5-point scale, and it must beat the control).

Hallucination control:
  * the prompt carries ONLY that district's own numbers — no retrieval, no
    world knowledge, no peer data beyond the peers we supply;
  * every fact is passed as a pre-formatted value, so the model is composing,
    not computing;
  * after generation, `verify_numbers` re-extracts every integer from the prose
    and asserts it appears in the district's own fact set. Any narrative that
    states a number we did not give it is REJECTED and the deterministic
    template is used instead. Fidelity is enforced, not hoped for.

    python3 -m mai.genai.g2_narrative --generate --limit 40
    python3 -m mai.genai.g2_narrative --judge --n 30
"""
import argparse
import json
import random
import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from mai import data as D                                  # noqa: E402
from mai import narrative as tmpl                          # noqa: E402
from mai.genai.client import GroqClient, model_for         # noqa: E402

OUT = D.CACHE / "v2" / "genai"

GEN_SCHEMA = {
    "type": "object",
    "properties": {"narrative": {"type": "string"}},
    "required": ["narrative"],
    "additionalProperties": False,
}

GEN_SYSTEM = """You write district market briefs for a pharmaceutical sales \
strategy team in India.

You will be given a JSON fact block for ONE district. Write a single paragraph \
of 60-100 words for a regional sales manager.

ABSOLUTE RULES
1. Use ONLY numbers that appear in the fact block. Never compute, round, \
estimate or invent a number. If you want to express something you were not \
given a number for, describe it in words instead.
2. Do not mention any place, disease statistic or fact that is not in the block.
3. Lead with the commercial implication, not the data. The reader wants to know \
what to do, not what the index says.
4. Name the specific therapy focus implied by the strongest pillar and the \
specific constraint implied by the weakest.
5. No preamble, no bullet points, no headings. One paragraph of prose.
6. Do not use the words "index", "pillar" or "score" more than once in total — \
write like a strategist, not a dashboard."""


def _facts(row, pillars, n):
    """The complete, pre-computed fact block. The model composes; it never
    calculates."""
    ps = {p: float(row[p]) for p in pillars if p in row and pd.notna(row[p])}
    ranked = sorted(ps.items(), key=lambda kv: -kv[1])
    lean = "chronic" if row["rank_chronic"] < row["rank_acute"] else "acute"
    return {
        "district": row["district_name"],
        "state": row["state_name"],
        "population_2011": (None if pd.isna(row["population"])
                            else int(row["population"])),
        "overall_rank": int(row["rank_overall"]),
        "districts_total": int(n),
        "rank_range_5_to_95_percent": [int(row["rank_lo_p5"]),
                                       int(row["rank_hi_p95"])],
        "chronic_rank": int(row["rank_chronic"]),
        "acute_rank": int(row["rank_acute"]),
        "therapy_lean": lean,
        "tier_band": str(row["tier"]),
        "strongest_dimensions": [
            {"name": tmpl.PILLAR_LABEL[k], "score_out_of_100": round(v)}
            for k, v in ranked[:2]],
        "weakest_dimension": (
            {"name": tmpl.PILLAR_LABEL[ranked[-1][0]],
             "score_out_of_100": round(ranked[-1][1])} if ranked else None),
        "suggested_focus": tmpl.ACTION.get(ranked[0][0]) if ranked else None,
        "current_rank": int(row["rank_current"]),
        "projected_future_rank": int(row["rank_future"]),
        "flagged_invest_ahead": bool(row["growth_flag"]),
    }


def _allowed_numbers(facts):
    """Every integer the model is permitted to state."""
    allowed = set()

    def walk(v):
        if isinstance(v, bool) or v is None:
            return
        if isinstance(v, (int, float)):
            allowed.add(int(round(v)))
        elif isinstance(v, dict):
            for x in v.values():
                walk(x)
        elif isinstance(v, list):
            for x in v:
                walk(x)
    walk(facts)
    # a brief may legitimately say "top 10" / "top 100" style round anchors
    allowed |= {10, 20, 25, 50, 100, 2011}
    return allowed


def verify_numbers(text, facts):
    """Return (ok, offending_numbers). Zero tolerance."""
    allowed = _allowed_numbers(facts)
    found = [int(x.replace(",", "")) for x in re.findall(r"\d[\d,]*", text)]
    bad = sorted({n for n in found if n not in allowed})
    return (not bad), bad


def generate_one(client, row, pillars, n):
    facts = _facts(row, pillars, n)
    out = client.chat("G2_GENERATE", GEN_SYSTEM,
                      json.dumps(facts, indent=1),
                      temperature=0.3, json_schema=GEN_SCHEMA,
                      # 90 words of prose is ~150 tokens; 700 leaves room for a
                      # short reasoning trace and still fits ~10 calls inside
                      # gpt-oss-20b's 8,000 TPM free-tier ceiling.
                      max_tokens=700, reasoning_effort="low")
    text = (out.get("narrative") or "").strip()
    ok, bad = verify_numbers(text, facts)
    return text, ok, bad, facts


def run_generate(limit=None, rpm=45):
    path = D.CACHE / "v2" / "scores_v2_with_intervals.csv"
    if not path.exists():
        sys.exit("run `python3 -m mai.validate` first")
    df = pd.read_csv(path, index_col=0)
    pillars = [c for c in df.columns if c.startswith(("P2_", "P3_", "P4_", "P5_"))]
    n = len(df)
    if limit:
        # a spread, not just the top: the brief must work for small districts too
        df = pd.concat([df.nsmallest(limit // 2, "rank_overall"),
                        df.sample(limit - limit // 2, random_state=42)])
        df = df[~df.index.duplicated()]

    client = GroqClient(per_minute=rpm)
    client.validate_roles(["G2_GENERATE"])
    print("G2 GENERATE — %d districts | model=%s"
          % (len(df), model_for("G2_GENERATE")))

    recs, rejected = {}, 0
    for i, (code, row) in enumerate(df.iterrows(), 1):
        try:
            text, ok, bad, facts = generate_one(client, row, pillars, n)
        except RuntimeError as e:
            # An API failure must degrade to the deterministic brief, not to a
            # hole in the output. Every district still gets a narrative, and
            # the reason it is not the LLM's is recorded per district.
            print("   %s api-failed -> template: %s" % (code, str(e)[:100]))
            fallback, _ = tmpl.narrative(row, pillars, n)
            recs[str(code)] = {"narrative": fallback, "source": "template_api_error",
                               "error": str(e)[:200]}
            continue
        if not ok:
            rejected += 1
            fallback, _ = tmpl.narrative(row, pillars, n)
            recs[str(code)] = {"narrative": fallback, "source": "template_fallback",
                               "rejected_numbers": bad, "llm_draft": text}
        else:
            recs[str(code)] = {"narrative": text, "source": "llm",
                               "model": model_for("G2_GENERATE")}
        if i % 25 == 0:
            print("   %d/%d …" % (i, len(df)))

    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / "g2_narratives.json", "w") as f:
        json.dump(recs, f, indent=1)

    n_llm = sum(1 for v in recs.values() if v["source"] == "llm")
    print("\n  generated              : %d" % len(recs))
    print("  passed numeric check   : %d (%.1f%%)"
          % (n_llm, 100 * n_llm / max(len(recs), 1)))
    print("  REJECTED -> template   : %d  (fidelity is enforced, not hoped for)"
          % rejected)
    print("  published fidelity     : 100%% by construction — a narrative that")
    print("                           states an ungrounded number never ships")
    print("  groq usage:", client.stats())
    return recs


JUDGE_SCHEMA = {
    "type": "object",
    "properties": {
        "brief_a_score": {"type": "integer"},
        "brief_b_score": {"type": "integer"},
        "better": {"type": "string", "enum": ["A", "B", "TIE"]},
        "reason": {"type": "string"},
    },
    "required": ["brief_a_score", "brief_b_score", "better", "reason"],
    "additionalProperties": False,
}

JUDGE_SYSTEM = """You are a regional sales director at an Indian pharmaceutical \
company. You are shown two district briefs written by different analysts about \
the SAME district.

Rate each 1-5 on ACTIONABILITY ONLY:
  5 = I know exactly which therapy area to push, through which channel, and \
what my main constraint is
  4 = clear direction, minor ambiguity
  3 = informative but I still have to decide what to do myself
  2 = mostly restates data
  1 = unusable

Judge only how useful it is for deciding where to send reps and what to detail. \
Ignore length and writing style. Do not reward jargon. You are not told which \
analyst wrote which brief.

Keep "reason" under 25 words."""


def run_judge(n=30, rpm=45, seed=42):
    """Blind A/B: LLM narrative vs deterministic template, shuffled."""
    gen_path = OUT / "g2_narratives.json"
    if not gen_path.exists():
        sys.exit("run --generate first")
    gen = json.load(open(gen_path))
    df = pd.read_csv(D.CACHE / "v2" / "scores_v2_with_intervals.csv", index_col=0)
    pillars = [c for c in df.columns if c.startswith(("P2_", "P3_", "P4_", "P5_"))]
    total = len(df)

    codes = [c for c in gen if gen[c]["source"] == "llm"]
    rng = random.Random(seed)
    rng.shuffle(codes)
    codes = codes[:n]

    client = GroqClient(per_minute=rpm)
    client.validate_roles(["G2_JUDGE"])
    print("G2 BLIND JUDGE — %d districts | judge=%s (generator was %s)"
          % (len(codes), model_for("G2_JUDGE"), model_for("G2_GENERATE")))
    print("  the judge is a DIFFERENT family from the generator by design\n")

    rows = []
    for i, code in enumerate(codes, 1):
        row = df.loc[int(code)] if int(code) in df.index else df.loc[code]
        control, _ = tmpl.narrative(row, pillars, total)
        treatment = gen[code]["narrative"]
        # randomise which slot the LLM occupies
        llm_is_a = rng.random() < 0.5
        a, b = (treatment, control) if llm_is_a else (control, treatment)
        user = "District brief A:\n%s\n\nDistrict brief B:\n%s" % (a, b)
        try:
            r = client.chat("G2_JUDGE", JUDGE_SYSTEM, user, temperature=0.0,
                            # llama-3.3-70b is not a reasoning model and the
                            # verdict is four short fields; a 1,200-token
                            # request buys nothing and burns the TPM ceiling.
                            json_schema=JUDGE_SCHEMA, max_tokens=400)
        except RuntimeError as e:
            print("   judge failed on %s: %s" % (code, str(e)[:100]))
            continue
        llm_score = r["brief_a_score"] if llm_is_a else r["brief_b_score"]
        ctl_score = r["brief_b_score"] if llm_is_a else r["brief_a_score"]
        winner = r["better"]
        llm_won = (winner == "A" and llm_is_a) or (winner == "B" and not llm_is_a)
        rows.append({"code": code, "llm_score": llm_score,
                     "template_score": ctl_score,
                     "llm_won": llm_won, "tie": winner == "TIE",
                     "reason": r["reason"][:200]})
        if i % 10 == 0:
            print("   %d/%d …" % (i, len(codes)))

    out = pd.DataFrame(rows)
    out.to_csv(OUT / "g2_judge.csv", index=False)
    llm_mean = out["llm_score"].mean()
    ctl_mean = out["template_score"].mean()
    winrate = out["llm_won"].mean()

    print("\n  LLM narrative  mean actionability : %.2f   (bar >= 4.0)  -> %s"
          % (llm_mean, "PASS" if llm_mean >= 4.0 else "FAIL"))
    print("  template control mean             : %.2f" % ctl_mean)
    print("  LLM must beat the control         : %+.2f  -> %s"
          % (llm_mean - ctl_mean, "PASS" if llm_mean > ctl_mean else "FAIL"))
    print("  head-to-head win rate for the LLM : %.0f%% (ties %.0f%%)"
          % (100 * winrate, 100 * out["tie"].mean()))

    summary = {
        "n": int(len(out)),
        "llm_mean_actionability": round(float(llm_mean), 3),
        "template_mean_actionability": round(float(ctl_mean), 3),
        "delta": round(float(llm_mean - ctl_mean), 3),
        "llm_win_rate": round(float(winrate), 3),
        "generator_model": model_for("G2_GENERATE"),
        "judge_model": model_for("G2_JUDGE"),
        "bars": {"mean_actionability": 4.0, "must_beat_control": True},
        "verdict_mean": "PASS" if llm_mean >= 4.0 else "FAIL",
        "verdict_vs_control": "PASS" if llm_mean > ctl_mean else "FAIL",
        "caveat": "LLM-as-judge is a proxy for human rating, not a substitute. "
                  "The judge is a different family from the generator, but both "
                  "are LLMs and may share stylistic preferences.",
    }
    with open(OUT / "g2_judge_summary.json", "w") as f:
        json.dump(summary, f, indent=2)
    return out, summary


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--generate", action="store_true")
    ap.add_argument("--judge", action="store_true")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--n", type=int, default=30)
    ap.add_argument("--rpm", type=int, default=45)
    args = ap.parse_args()
    if args.generate:
        run_generate(limit=args.limit, rpm=args.rpm)
    if args.judge:
        run_judge(n=args.n, rpm=args.rpm)
    if not (args.generate or args.judge):
        ap.print_help()


if __name__ == "__main__":
    main()
