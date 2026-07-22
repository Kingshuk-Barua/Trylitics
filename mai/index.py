"""MAI v2 composite.

Two structural changes from v1, both driven by the audit.

1. RANK NORMALISATION IS THE HEADLINE (replaces winsorise -> min-max).

   Every indicator becomes its percentile rank within the scored set, signed by
   direction. This is not a cosmetic swap; it fixes four findings at once:

     M-13  vintage. A district's population RANK is far more stable across 15
           years than its 2011 absolute count. Ranking is the honest way to use
           a 2011 frame for a 2026 decision — we assert ordering, which has
           held, not levels, which have not.
     M-19  winsorisation order. Ranks are invariant to any monotone transform,
           so outlier treatment and the impute-then-winsorise ordering bug stop
           mattering. Winsorisation is dropped entirely, not merely reordered.
     M-07  discrimination. Min-max over skewed indicators piled every district
           near the middle (observed range 28.5 of 100). Percentile ranks are
           uniform by construction, so the composite uses its whole scale.
     C-04  residual population error. Chennai's mirror figure is still ~1.5x
           the published Census count; its RANK among 698 districts is
           essentially unaffected.

   Min-max and z-score are retained as sensitivity arms (see `sensitivity.py`).

2. MARKET SIZE IS A MULTIPLICATIVE FACTOR, NOT A PILLAR (C-01/C-02/C-07).

   v1 averaged min-maxed log10(population) with two percentages inside a
   'P1_scale' pillar. log10 compressed a 3-order-of-magnitude range into 2.5
   points, urbanisation then dominated the pillar (60% of its variance), and
   the headline index ended up rank-correlated 0.253 with population — so
   deploying to the top-100 MAI districts captured LESS opportunity (22.8%)
   than deploying to the 100 largest (40.9%).

   v2 uses the market-potential formulation the plan itself cites (MSU-CIBER
   MPI, plan section 1):

       MAI = 100 * Size^alpha * Quality^(1-alpha)

   Size is the rank-percentile patient pool; Quality is the weighted composite
   of burden, access, affordability and momentum. The geometric form gives
   partial compensability — the plan's own section 3.7 requirement — so a huge
   district with no affordability and a tiny affluent one are both penalised,
   and neither can hide behind a single strong factor.
"""
import numpy as np
import pandas as pd

from .features import PILLARS, SIZE

# Quality weights. Renormalised over whatever pillars a given index uses.
# Burden 0.40 / access 0.25 / affordability 0.25 / momentum 0.10 within Quality;
# size then re-enters through alpha. Under the v1 scheme the equivalent
# size share was nominally 0.25 but effectively ~0.09 after log compression.
W_QUALITY = {
    "P2_chronic": 0.20,
    "P2_acute": 0.20,
    "P3_access": 0.25,
    "P4_afford": 0.25,
    "P5_mom_chronic": 0.035,
    "P5_mom_acute": 0.035,
    "P5_mom_adoption": 0.03,
}

ALPHA = 0.50            # geometric weight on size vs quality
ALPHA_FUTURE = 0.45     # the forward view leans slightly less on today's size

# Which pillars each index uses. Chronic and acute now differ in BOTH their
# burden pillar and their momentum pillar (M-01/M-06), instead of sharing 0.75
# of their weight as in v1.
INDEX_PILLARS = {
    "overall": ["P2_chronic", "P2_acute", "P3_access", "P4_afford",
                "P5_mom_chronic", "P5_mom_acute", "P5_mom_adoption"],
    "chronic": ["P2_chronic", "P3_access", "P4_afford",
                "P5_mom_chronic", "P5_mom_adoption"],
    "acute": ["P2_acute", "P3_access", "P4_afford",
              "P5_mom_acute", "P5_mom_adoption"],
}


def rank_normalise(s, direction=1):
    """Percentile rank in [0, 100]. Ties averaged. NaNs stay NaN."""
    r = s.rank(pct=True, na_option="keep")
    if direction < 0:
        r = 1.0 - r
    return r * 100.0


def minmax_normalise(s, direction=1):
    lo, hi = s.min(), s.max()
    n = (s - lo) / (hi - lo) * 100.0 if hi > lo else s * 0 + 50.0
    return 100.0 - n if direction < 0 else n


def z_normalise(s, direction=1):
    z = (s - s.mean()) / (s.std() if s.std() else 1.0)
    if direction < 0:
        z = -z
    return 50.0 + 10.0 * z


NORMALISERS = {"rank": rank_normalise, "minmax": minmax_normalise,
               "z": z_normalise}


def normalise_matrix(X, directions, method="rank"):
    fn = NORMALISERS[method]
    return pd.DataFrame({f: fn(X[f], directions[f]) for f in X.columns},
                        index=X.index)


def pillar_scores(N, pillars=None, drop_indicator=None):
    """Mean of the normalised indicators inside each pillar."""
    pillars = pillars or PILLARS
    out = {}
    for p, fields in pillars.items():
        fl = [f for f in fields if f in N.columns and f != drop_indicator]
        if fl:
            out[p] = N[fl].mean(axis=1)
    return pd.DataFrame(out, index=N.index)


# Prevalence indicators used to turn headcount into a THERAPY-SPECIFIC patient
# pool. Audit M-02 noted the therapy split had "no prevalence-to-patient-pool
# conversion"; this is that conversion.
CHRONIC_PREVALENCE = ["wom_bld_sugar_high", "men_bld_sugar_high",
                      "wom_bp_ele_med", "men_bp_ele_med", "wom_obese"]
ACUTE_PREVALENCE = ["child_6_59_anemic", "wom_15_49_anaemic",
                    "cd_ari_2wks", "cd_drh_2wks"]


def size_score(X, method="rank", pool=None):
    """The patient-pool factor.

    Population enters at its raw percentile rank — no log, no min-max — so the
    ordering that matters for revenue survives intact (C-02).

    `pool` makes the factor therapy-specific. A first cut that used ONE shared
    size factor for all three indices pushed Spearman(chronic, acute) from
    0.676 to 0.963: with size at half the geometric weight and identical across
    indices, the therapy split collapsed. The brief requires three distinct
    indices, so the pool itself must differ:

        overall  = population
        chronic  = population x mean(chronic prevalence) x adult share
        acute    = population x mean(acute prevalence)

    which is also the more defensible construct — an addressable patient count
    rather than a headcount.
    """
    pop = X["population"].astype(float)
    if pool == "chronic":
        prev = X[[c for c in CHRONIC_PREVALENCE if c in X.columns]].mean(axis=1) / 100.0
        adult = (100.0 - X["pop_below_15"]) / 100.0 if "pop_below_15" in X.columns else 1.0
        pool_size = pop * prev * adult
    elif pool == "acute":
        prev = X[[c for c in ACUTE_PREVALENCE if c in X.columns]].mean(axis=1) / 100.0
        pool_size = pop * prev
    else:
        pool_size = pop
    s = NORMALISERS[method](pool_size, +1)
    urb = NORMALISERS[method](X["urban_share"], +1)
    return 0.75 * s + 0.25 * urb


def combine(size, quality, alpha=ALPHA):
    """MAI = 100 * (size/100)^alpha * (quality/100)^(1-alpha).

    Floored at 1 to keep the log finite; with rank normalisation the minimum
    is ~0.14 so the floor binds on at most one district and is recorded.
    """
    s = np.clip(size, 1.0, 100.0) / 100.0
    q = np.clip(quality, 1.0, 100.0) / 100.0
    return 100.0 * np.power(s, alpha) * np.power(q, 1.0 - alpha)


def quality_score(PS, index="overall", weights=None, blocked=None):
    """Weighted mean of the pillars this index uses.

    `blocked` is the boolean (district x pillar) frame from the <1/3 rule
    (audit C-06). Where a pillar is blocked for a district, its weight is
    RE-ALLOCATED across that district's remaining pillars rather than the
    pillar being median-filled. This is the NITI Aayog State Health Index
    convention, confirmed in the audit (M-20): "if data were missing ... that
    indicator was dropped ... and the indicator weight was re-allocated to
    other indicators within the same domain".
    """
    w = dict(weights or W_QUALITY)
    cols = [p for p in INDEX_PILLARS[index] if p in PS.columns]
    wv = pd.DataFrame(
        np.tile([w[c] for c in cols], (len(PS), 1)),
        index=PS.index, columns=cols, dtype=float)
    if blocked is not None:
        mask = blocked.reindex(index=PS.index, columns=cols).fillna(False)
        wv = wv.mask(mask, 0.0)
        # a district with every pillar blocked falls back to equal weights
        allzero = wv.sum(axis=1) == 0
        if allzero.any():
            wv.loc[allzero] = 1.0
    wv = wv.div(wv.sum(axis=1), axis=0)
    return (PS[cols].fillna(0.0) * wv).sum(axis=1)


def build_indices(X, directions, method="rank", alpha=ALPHA,
                  weights=None, aggregation="geometric", drop_indicator=None,
                  blocked=None):
    """Full composite. Returns (scores DataFrame, pillar scores, size series)."""
    N = normalise_matrix(X, directions, method)
    PS = pillar_scores(N, drop_indicator=drop_indicator)
    S = size_score(X, method)

    out = pd.DataFrame(index=X.index)
    for idx in ("overall", "chronic", "acute"):
        Q = quality_score(PS, idx, weights, blocked)
        Si = size_score(X, method, pool=(idx if idx != "overall" else None))
        if aggregation == "geometric":
            out["mai_" + idx] = combine(Si, Q, alpha)
        else:                                  # arithmetic sensitivity arm
            out["mai_" + idx] = alpha * Si + (1 - alpha) * Q
        out["quality_" + idx] = Q
        out["size_" + idx] = Si

    # Current vs future (plan section 6).
    #
    # Re-weighting quality alone is not enough to separate the two views: size
    # carries half the geometric weight and is identical across them, so a
    # momentum re-weight moved Spearman(current, future) only to 0.991. The
    # forward view must therefore project the PATIENT POOL forward, not just
    # re-weight today's quality — which is also what the brief asks for
    # ("how district level opportunity is expected to evolve").
    #
    # Growth multiplier: districts in the top momentum decile get up to +30%
    # projected pool, the bottom decile -10%. The band is a stated assumption,
    # not an estimate, and the sensitivity analysis varies it.
    w_cur = {k: v for k, v in (weights or W_QUALITY).items()
             if not k.startswith("P5_")}
    out["mai_current"] = combine(
        S, quality_score(PS, "overall", _fill(w_cur), blocked), alpha)

    mom_cols = [c for c in PS.columns if c.startswith("P5_")]
    momentum_pct = PS[mom_cols].mean(axis=1).rank(pct=True)
    growth = 0.90 + 0.40 * momentum_pct          # 0.90 .. 1.30
    S_future = (S * growth).rank(pct=True) * 100.0

    w_fut = dict(weights or W_QUALITY)
    for k in list(w_fut):
        if k.startswith("P5_"):
            w_fut[k] *= 3.0
    out["mai_future"] = combine(
        S_future, quality_score(PS, "overall", w_fut, blocked), ALPHA_FUTURE)

    out["size_score"] = S
    out["size_future"] = S_future
    return out, PS, S


def _fill(w):
    """quality_score needs a weight for every pillar it is handed; pillars
    absent from the dict are given zero."""
    full = {k: 0.0 for k in W_QUALITY}
    full.update(w)
    return full


def add_ranks_and_tiers(scores, pillar_scores_df):
    for c in ("overall", "chronic", "acute", "current", "future"):
        scores["rank_" + c] = scores["mai_" + c].rank(ascending=False).astype(int)
    # Tiers stay a decile-style banding of the index and are labelled as such.
    # The audit (M-15) established that a classifier trained on them is a
    # lookup table; they are presented as bands, never as a model output.
    scores["tier"] = pd.qcut(scores["mai_overall"], 4,
                             labels=["D", "C", "B", "A"])
    mom = [c for c in pillar_scores_df.columns if c.startswith("P5_")]
    momentum = pillar_scores_df[mom].mean(axis=1)
    scores["momentum_score"] = momentum
    # 'invest ahead': momentum in the top quartile while the current index is
    # outside the top 100. Continuous companion published alongside so the
    # flag is not a hard cliff (m-13).
    scores["growth_gap"] = momentum.rank(pct=True) * 100 - \
        scores["mai_current"].rank(pct=True) * 100
    scores["growth_flag"] = ((momentum > momentum.quantile(0.75)) &
                             (scores["rank_current"] > 100))
    return scores
