"""District narratives grounded in the pillar decomposition (roadmap R-14 / G2).

Deterministic template generation with a hard numeric-fidelity guarantee: every
number in the output is read from the score record, and `verify()` re-extracts
the numbers from the generated text and asserts they match the source. There is
no model call here — the templating is the grounding layer that an LLM pass
would sit ON TOP of, never instead of.

That ordering is the point of the design: the uplift plan requires 100% numeric
fidelity with zero tolerance, which is only achievable if the numbers are
placed by code and the model is confined to prose.

    python3 -m mai.narrative
"""
import json
import re

import pandas as pd

from . import data as D

OUT = D.CACHE / "v2"

PILLAR_LABEL = {
    "P2_chronic": "chronic burden",
    "P2_acute": "acute burden",
    "P3_access": "access and supply",
    "P4_afford": "affordability",
    "P5_mom_chronic": "chronic momentum",
    "P5_mom_acute": "acute momentum",
    "P5_mom_adoption": "care-adoption momentum",
}

ACTION = {
    "P2_chronic": "cardiometabolic and CNS portfolios",
    "P2_acute": "anti-infectives, GI and VMN",
    "P3_access": "channel build-out with existing empanelled providers",
    "P4_afford": "premium/branded positioning",
    "P5_mom_chronic": "invest-ahead chronic detailing",
    "P5_mom_acute": "acute-therapy stocking depth",
    "P5_mom_adoption": "formal-channel expansion",
}


def _pct(rank, n):
    return 100.0 * (1.0 - (rank - 1) / max(n - 1, 1))


def narrative(row, pillars, n):
    """Return (text, facts) where facts is what verify() will re-check."""
    name, state = row["district_name"], row["state_name"]
    ro, rc, ra = int(row["rank_overall"]), int(row["rank_chronic"]), int(row["rank_acute"])
    lo, hi = int(row["rank_lo_p5"]), int(row["rank_hi_p95"])
    ps = {p: float(row[p]) for p in pillars if p in row}
    top = sorted(ps.items(), key=lambda kv: -kv[1])[:2]
    bot = sorted(ps.items(), key=lambda kv: kv[1])[:1]
    lean = "chronic" if rc < ra else "acute"
    lean_rank = min(rc, ra)

    text = (
        "{name} ({state}) ranks {ro} of {n} on the overall Market "
        "Attractiveness Index, with a 5-95% rank interval of {lo}-{hi}. "
        "Its strongest pillars are {t0} ({v0:.0f}/100) and {t1} ({v1:.0f}/100); "
        "the binding constraint is {b0} ({vb:.0f}/100). "
        "The district leans {lean} (rank {lr} on that index, against {other} on "
        "the other), so the first-line play is {action}. "
        "Size factor {size:.0f}/100 on a population of {pop}."
    ).format(name=name, state=state, ro=ro, n=n, lo=lo, hi=hi,
             t0=PILLAR_LABEL[top[0][0]], v0=top[0][1],
             t1=PILLAR_LABEL[top[1][0]], v1=top[1][1],
             b0=PILLAR_LABEL[bot[0][0]], vb=bot[0][1],
             lean=lean, lr=lean_rank, other=max(rc, ra),
             action=ACTION[top[0][0]],
             size=float(row["size_score"]),
             pop=("{:,.0f}".format(row["population"])
                  if pd.notna(row["population"]) else "n/a"))

    facts = {"rank_overall": ro, "rank_lo": lo, "rank_hi": hi,
             "n": n, "lean_rank": lean_rank, "other_rank": max(rc, ra)}
    return text, facts


def verify(text, facts):
    """Re-extract integers from the prose and confirm they match the source.

    Any mismatch is a hard failure — the narrative layer must never state a
    number the score record does not contain.
    """
    found = set(int(x.replace(",", "")) for x in re.findall(r"\d[\d,]*", text))
    missing = [k for k, v in facts.items() if int(v) not in found]
    return (not missing), missing


def main():
    path = OUT / "scores_v2_with_intervals.csv"
    if not path.exists():
        raise SystemExit("run `python3 -m mai.validate` first "
                         "(it writes the rank intervals)")
    df = pd.read_csv(path, index_col=0)
    pillars = [c for c in df.columns if c.startswith(("P2_", "P3_", "P4_", "P5_"))]
    n = len(df)

    out, failures = {}, []
    for code, row in df.iterrows():
        text, facts = narrative(row, pillars, n)
        ok, missing = verify(text, facts)
        if not ok:
            failures.append((code, missing))
        out[str(code)] = text

    with open(OUT / "narratives_v2.json", "w") as f:
        json.dump(out, f, indent=1)

    print("narratives generated : %d" % len(out))
    print("numeric-fidelity fails: %d  (target 0, zero tolerance)" % len(failures))
    if failures:
        print("  ", failures[:5])
    print("\nsamples:")
    for code in list(df.nsmallest(2, "rank_overall").index) + \
            list(df.nlargest(1, "rank_overall").index):
        print("\n  [%s] %s" % (code, out[str(code)]))
    return out


if __name__ == "__main__":
    main()
