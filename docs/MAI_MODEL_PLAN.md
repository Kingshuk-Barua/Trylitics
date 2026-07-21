# MAI Model Plan — District Market Attractiveness Index (analysis & design only)

> Status: **PLAN** (no code yet, per user instruction 2026-07-17). Methodology
> decisions locked with user: **hybrid** (transparent composite backbone + ML
> in supporting roles), research scope = industry practice + academic
> composite-index science. Sources: deep-research run over OECD/JRC handbook,
> JRC-COIN materials, NITI Aayog Health Index, IQVIA IPM reports, EVERSANA,
> MSU-CIBER MPI (see §9; adversarial verification pass was blocked by session
> limits — claims are grounded in fetched sources but flagged unverified).

## 1. Concept: five pillars + a momentum overlay

The user's three drivers (disease burden → demand, hospitals → access,
economics → affordability) formalized, with two additions our data uniquely
supports:

| Pillar | Question it answers | Weight home |
|---|---|---|
| P1 Market Scale | How many patients can this district ever hold? | size-dominant, per MSU-CIBER MPI precedent (Market Size 25/100) |
| P2 Disease Burden | How much treatable illness is there (split chronic/acute)? | core demand signal |
| P3 Access & Supply | Can patients reach treatment (hospitals, public/private mix)? | industry "accessibility" criterion (EVERSANA) |
| P4 Affordability | Can households pay (income, deprivation, insurance, OOP)? | affordability/payer mix |
| P5 Momentum | Is the market growing (NFHS-4→5 deltas, current TB, demographics)? | the forward-looking view |

Three indices from one indicator tree: **Overall** (all pillars), **Chronic**
(P2/P5 restricted to chronic indicators), **Acute** (P2/P5 acute indicators).
P1/P3/P4 are shared context pillars across all three.

## 2. Indicator inventory (mapped to our actual Firestore collections)

Direction: (+) raises attractiveness, (−) lowers it.

**P1 Market Scale** — `census_pca`: population_2011 total/urban/rural (+),
pop_0_6 (pediatric segment share); `districts`: state/region context.

**P2 Chronic burden** — `district_indicators.nfhs.2019_20`: high blood sugar
(wom/men) (+), elevated BP (+), obesity/BMI (+), tobacco & alcohol use (+)
[risk-factor pipeline]. Maps to IQVIA chronic TAs: Cardiac, Anti-Diabetes,
Respiratory-Chronic, CNS.

**P2 Acute burden** — `tb_live`: current-year notifications per lakh (+),
private-notification share (+ = private market exists); NFHS: anaemia (+),
ARI/diarrhoea child indicators (+), sanitation/water deficits (+). Maps to
IQVIA acute TAs: Anti-Infectives, GI, VMN.

**P3 Access & Supply** — `pmjay_hospitals`: hospitals per lakh (+), private
share (+ for branded-generics channel); NFHS: institutional births (+),
skilled-personnel births (+) as access proxies.

**P4 Affordability** — `secc`: mon_inc_gt_10k share (+), deprivation share (−),
affluence markers (motor vehicle, refrigerator…) (+); NFHS: health-insurance
coverage (+), out-of-pocket expenditure (context, direction per therapy);
PCA literacy (+).

**P5 Momentum** — NFHS 2014_15→2019_20 deltas of the P2 indicators (+ when
burden rising), insurance-coverage delta (+), population growth proxy, TB
current-year vs NFHS-era baseline.

## 3. Method — OECD/JRC 10-step aligned

1. **Framework** — the pillar tree above; every indicator documented in
   `indicator_catalog` (code, pillar, direction, source, rationale).
2. **Data selection & coverage rules** (JRC-COIN thresholds): keep an
   indicator only if ≥80% of districts have valid values; impute only when
   <⅓ missing. Post-2011 districts inherit parent values, `is_imputed=true`.
3. **Imputation** — within-state median for scattered gaps; parent-district
   inheritance for splits; every imputation logged.
4. **Multivariate analysis** — correlation matrix + PCA per pillar: confirm
   indicators within a pillar cohere and drop redundant near-duplicates.
5. **Outlier treatment & normalization** — JRC rule: |skew|>2 AND kurtosis>3.5
   → winsorize toward the 2.5/97.5th percentiles. Then **min-max to 0–100**
   with direction inversion for (−) indicators — the NITI Health Index
   convention, familiar to Indian judges. (Z-score variant kept as a
   sensitivity check, since z-scores amplify extremes.)
6. **Weighting (hybrid, pillar-level)** — weight at the PILLAR level, never
   the raw-variable level (equal weights over nested variables silently
   over-weight indicator-rich pillars — OECD Handbook warning). Three schemes:
   *business* budget-allocation weights (size-dominant, MSU-CIBER-style
   starting point: Scale 25, Burden 25, Access 20, Affordability 15,
   Momentum 15), *data-driven* PCA and entropy weights. Headline = business
   weights; the other two reported as robustness (rank correlations shown).
7. **Aggregation** — headline: **weighted arithmetic mean** (NITI Health
   Index formula, fully explainable). Companion: **geometric mean** variant —
   partial compensability penalizes districts with one crippling weakness
   (huge population but no affordability). Divergence between the two flags
   unbalanced districts — itself an insight for sales-force strategy.
8. **Uncertainty & sensitivity analysis** (mandatory, Handbook step 7;
   Saisana-Saltelli method): Monte-Carlo perturbation of pillar weights
   (±25%), normalization swap (min-max↔z), aggregation swap (arith↔geom),
   leave-one-indicator-out. Report **rank intervals** per district and
   top-50 stability share. This is the single strongest judge-defense move —
   JRC audits 100+ published indices exactly this way.
9. **Back to the data** — profile the top/bottom districts; SHAP-style
   decomposition of each district's score into pillar contributions (the app's
   drill-down view).
10. **Visualisation** — the Firebase app: choropleth, rankings, drill-down,
    chronic/acute toggle, current-vs-future toggle.

## 4. ML roles (the "hybrid" agreed with user)

- **PCA** — pillar coherence check + alternative weights (Social Progress
  Index precedent).
- **Entropy weighting** — information-content weights, second data-driven pole.
- **K-means clustering** on pillar scores → 4–6 district archetypes
  ("metro-mature", "emerging-chronic", "acute-underserved"…) → tier labels
  A/B/C/D for the sales-force lens.
- **Gradient boosting + SHAP as validation, not scoring**: predict a proxy
  demand target (see §5) from pillar scores; SHAP shows which pillars drive
  predicted demand — evidence the index is not arbitrary. The model never
  replaces the transparent score.

## 5. Proxy strategy for missing sales data

Precedent: MSU-CIBER MPI builds national market-size scores from indirect
proxies (electricity consumption, urban population) — proxy-based demand
estimation is institutionally normal. Our proxy stack for district pharma
demand: TB **private**-notification share (revealed private-market activity),
PMJAY private-hospital density (private supply follows demand),
NFHS out-of-pocket spend level, affluence/income markers. State-level IPM
figures (IQVIA public reports: Chronic 37%/Acute 63% value split; metro/
class-1/ex-urban ≈ 32/32/36) anchor plausibility checks — notably, ex-urban
markets are the LARGEST slice, so a non-metro-skewed index is defensible.

## 6. Current-vs-future view

NITI Health Index precedent: publish BOTH level ("performance") and delta
("incremental") views. MAI-Current = P1–P4 levels + current TB. MAI-Future =
re-weighted with P5 doubled + P2 momentum-adjusted. `growth_flag` = high
P5 & mid P1 → "invest-ahead" districts.

## 7. Validation without ground truth (judge checklist)

1. Face validity: known metro/tier-1 districts land high; spot-check 10.
2. Convergent validity: correlate Overall vs NITI district indicators / MPI
   where overlapping — expect moderate positive, not 1.0.
3. IPM anchors: chronic-index state aggregates vs IQVIA chronic share.
4. Rank-stability report from §3.8.
5. Full assumptions log (`mai_runs` doc per model version).

## 8. Execution phases (when user says go — each ends in a reviewable artifact)

1. **Crosswalk** (`dim_district`): LGD-spine join of NFHS codes ↔ PCA/SECC ↔
   factsheet names ↔ Ni-kshay/PMJAY state-district labels ↔ geoBoundaries
   shapeIDs. Hardest single step; fuzzy name-matching + manual review file.
2. **Feature matrix**: ~730 districts × ~40 indicators from Firestore/raw,
   coverage report, imputation log.
3. **Model v1**: steps 1–7 above → `mai_scores` (overall/chronic/acute +
   ranks + tiers + current/future) published to Firestore.
4. **Robustness pack**: sensitivity runs → rank intervals → `mai_runs`.
5. **Segmentation**: clustering + SHAP validation → tier labels.
6. **Demo app**: Firebase Hosting SPA (map + rankings + drill-down + toggles).
7. **Deck**: methodology story, robustness evidence, sales-force actionability.

## 9. Sources (fetched; adversarial verification pending — see note)

OECD/JRC Handbook on Constructing Composite Indicators (10 steps, weighting/
aggregation/robustness) · JRC EUR 21682 (Saisana-Saltelli sensitivity) ·
JRC-COIN/ITU slides (skew/kurtosis outlier rule, coverage thresholds, scheme
census) · knowledge4policy.ec.europa.eu (JRC audit practice) · COINr package
docs · NITI Aayog State Health Index report (min-max, judgmental domain
weights, two-view) · IQVIA IPM quarterly insights (chronic/acute taxonomy &
shares, town-class split) · EVERSANA launch-sequencing whitepaper ·
MSU-CIBER Market Potential Index. Verification note: the 3-vote adversarial
pass failed on session limits twice (2026-07-17); claims match fetched source
text but re-verify before quoting numbers in the final deck.
