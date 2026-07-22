# Trilytics MAI — District-Level Market Attractiveness Index (Sun Pharma case)

A reproducible pipeline that scores **698 Indian districts** on pharmaceutical
market attractiveness from free government/academic sources, validates the
index against thresholds fixed before the numbers existed, and publishes the
result to **Cloud Firestore** (`medicine-attractive-index`), which a Next.js
dashboard reads at runtime.

```
 SOURCES ──► pipeline/         raw payloads, hash-checked, kept locally
                │                       │
                │ aggregate             │ upsert (write-budgeted)
                ▼                       ▼
        data/raw/<source>/        Firestore: districts, secc, census_pca,
                                  tb_live, pmjay_hospitals, …
                                          │
                                          │ 00_pull_firestore.py (READ ONLY)
                                          ▼
                                  analysis/audit/_cache/*.pkl
                                          │
                                  mai/    │ build → validate → ml → benchmarks
                                          │ → narrative → genai
                                          ▼
                                  analysis/audit/_cache/v2/   (all results, local)
                                          │
                                          │ python3 -m mai.publish --confirm
                                          ▼
                                  Firestore: mai_scores (698) + mai_runs (1)
                                          │
                                          ▼
                                  web/ dashboard  ·  deck/ submission PPTX
```

**Nothing is written to Firestore until you ask for it.** Every model step
writes to `analysis/audit/_cache/v2/` and is read-only with respect to the
database; `mai.publish` is a dry run unless you pass `--confirm`.

---

## 1. Install

Python ≥ 3.9 (macOS system Python is fine). Node ≥ 18 only if you want the web app.

```bash
cd /path/to/Trylitics
pip3 install -r requirements.txt
```

## 2. Credentials

Credentials resolve **environment first**, then the git-ignored `Credentials/`
folder. `pipeline/config.py` auto-loads `.env` on import — no `source` needed,
and real shell variables always win.

```bash
cp .env.example .env      # then fill in the values
```

| Credential | `.env` variable | Fallback file | Needed for |
|---|---|---|---|
| **Firebase Admin SDK key** | `FIREBASE_SERVICE_ACCOUNT_JSON` (whole JSON on one line, single-quoted, or base64) — or a path in `FIREBASE_CREDENTIALS_PATH` | `Credentials/Firebase_Service_Account.json` | pulling the snapshot, publishing |
| **data.gov.in API key** | `DATA_GOV_IN_API_KEY` | `Credentials/DATA_GOV_IN_API_KEY.json` | one source (NFHS-5 factsheet) |
| **Groq API key** | `GROQ_API_KEY` (plus `GROQ_API_KEY_2` … `_8`, or a comma-separated `GROQ_API_KEYS`) | `Credentials/Groq.json` | the optional GenAI layer only |

The Firebase service account needs the **Firebase Admin SDK Administrator
Service Agent** role (or broader) in
[IAM](https://console.cloud.google.com/iam-admin/iam?project=medicine-attractive-index).

No key is required for India Data Portal (CKAN), Ni-kshay, PMJAY, geoBoundaries
or DHS.

---

## 3. Ingest — sources → local raw → Firestore

Skip this section entirely if the Firestore collections are already populated
and you only want to rebuild the index; go to §4.

```bash
python3 -m pipeline.run --status              # where things stand (safe anytime)
python3 -m pipeline.run --once                # run every DUE source once, then exit
python3 -m pipeline.run --once --force        # ignore cadence, run everything now
python3 -m pipeline.run --once --no-publish   # fetch + save raw only, no Firestore
python3 -m pipeline.run --source nikshay_tb   # one source (comma-separated for several)
python3 -m pipeline.run --daemon              # continuous mode for a live demo
```

Source ids: `idp_nfhs` `datagovin_nfhs5` `idp_secc` `geoboundaries` `nikshay_tb`
`idp_pca` `pmjay_hospitals` `idp_hmis` `dhs_state` `shrug`.

Raw payloads land verbatim in `data/raw/<source>/ingest_<ts>/`; resume state
lives in `data/state/pipeline_state.json`. Unchanged content (sha256) is not
re-published, so idle cycles cost nothing. One instance at a time
(`data/state/pipeline.lock`).

`--daemon` re-checks every 60 s: Ni-kshay TB hourly, NFHS/SECC/factsheet/PMJAY
daily, PCA/HMIS/geo/DHS/SHRUG weekly.

**One optional repair** — if you have re-pulled Census PCA, regenerate the
corrected population aggregation before building (audit C-04):

```bash
python3 -m pipeline.run --source idp_pca --no-publish
python3 -m mai.fix_pca            # -> analysis/audit/_cache/pca_fixed.json
```

## 4. Snapshot Firestore locally

The model never reads Firestore directly. Pull once into a pickle cache:

```bash
python3 analysis/audit/00_pull_firestore.py
```

Read-only — this script never calls set/update/delete. Writes
`analysis/audit/_cache/<collection>.pkl` plus a `manifest.json`. Every
subsequent step is offline, which is what makes the build reproducible and its
input hashes meaningful.

## 5. Build and validate the index

Run in this order. Each command prints its own results and writes artefacts to
`analysis/audit/_cache/v2/`.

```bash
python3 -m mai.build          # 1. the index itself
python3 -m mai.validate       # 2. 31 tests + rank intervals  (REQUIRED before publish)
python3 -m mai.ml             # 3. supervised falsification, state-blocked CV
python3 -m mai.benchmarks     # 4. external convergent validity
python3 -m mai.narrative      # 5. deterministic district briefs
python3 -m mai.reproduce --selftest   # 6. reproducibility + staleness detector
```

| Command | Writes | What it is |
|---|---|---|
| `mai.build` | `scores_v2.csv`, `pillar_scores_v2.csv`, `features_imputed_v2.csv`, `run_v2.json`, `imputation_flags_v2.json`, coverage/provenance/audit CSVs | Crosswalk → 42 indicators → coverage gate → impute → rank-normalise → 7 pillars → `MAI = 100·Size^0.5·Quality^0.5`, plus chronic/acute/current/future |
| `mai.validate` | **`scores_v2_with_intervals.csv`**, `validation_v2.csv`, imputation-sensitivity CSVs | Four validation layers, 31 pre-registered tests, Monte-Carlo rank intervals |
| `mai.ml` | `ml_validation_v2.json` | Tries to *break* the index: predicts revealed private demand from the pillars under `GroupKFold` blocked by state |
| `mai.benchmarks` | `benchmarks_v2.csv/.json` | NITI Aayog SHI and SECC income; records what is BLOCKED rather than skipping it |
| `mai.narrative` | `narratives_v2.json` | Template briefs whose every number is placed by code and re-verified from the text |
| `mai.reproduce` | `reproducibility_v2.csv/.json`, `staleness_v2.csv` | Rebuilds from scratch and compares at 2 dp; re-hashes inputs. `--selftest` proves the staleness detector fires; `--skip-rerun` checks staleness only |

`mai.validate` is not optional: `mai.publish` refuses to run without
`scores_v2_with_intervals.csv`.

## 6. Optional — the GenAI layer

Needs `GROQ_API_KEY`. Skip it and everything still works: publishing falls back
to the deterministic templates from `mai.narrative`.

```bash
python3 -m mai.genai.g1_crosswalk --eval  --n 60 --rpm 25   # measure precision first
python3 -m mai.genai.g1_crosswalk --resolve --rpm 18        # then resolve open labels
python3 -m mai.genai.g2_narrative  --generate --rpm 10      # write briefs
python3 -m mai.genai.g2_narrative  --judge --n 30 --rpm 10  # blind A/B vs the template
```

Roles use **different model families on purpose** — the verifier must not be the
proposer, the judge must not be the generator — and each call is checked by
code that can reject it. Artefacts land in `analysis/audit/_cache/v2/genai/`.

If a model exhausts its **per-day** token allowance the client rotates to the
next `GROQ_API_KEY_n` on the *same* model, and only then to a declared
alternate family, printing the substitution. Lower `--rpm` if you hit
per-minute limits.

## 7. Publish to Firestore

**Dry run by default.** Look at the output before you commit.

```bash
python3 -m mai.publish             # prints the document count, narrative
                                   # provenance and a sample doc. Writes nothing.
python3 -m mai.publish --confirm   # 698 mai_scores + 1 mai_runs
```

What `--confirm` does:

- upserts `mai_scores/{district_code}` — scores, ranks, tiers, rank intervals,
  pillar decomposition, `is_imputed`, the narrative and its provenance, the
  `run_id` and the input-snapshot hash it was built from;
- upserts `mai_runs/{model_version}` — the full run record (weights, method,
  seed, git SHA, vintages, coverage, imputation);
- goes through `pipeline.publish.firestore.publish_docs`, so the writes count
  against the daily budget in `data/state/pipeline_state.json`
  (`FIRESTORE_DAILY_WRITE_CAP`, default 15,000 — this run costs 699);
- writes with `merge=True`, so it updates the existing documents rather than
  replacing the collection.

If the budget is short the call raises `QuotaDeferred` and writes nothing —
rerun after the daily reset rather than raising the cap.

## 8. The dashboard

```bash
cd web
npm install
cp .env.local.example .env.local     # NEXT_PUBLIC_FIREBASE_* web config
npm run dev                          # http://localhost:3000
npm run build                        # static export to out/
firebase deploy --only hosting       # optional
```

Reads `mai_scores` + `mai_runs` from the browser once per session. With no
Firebase config, or if the read fails, it falls back to the bundled snapshot in
`web/public/data/` and says so in the status bar. See [web/README.md](web/README.md).

## 9. The submission deck

Regenerates every figure from the artefacts in `_cache/v2` — nothing is pasted
in by hand:

```bash
python3 deck/make_maps.py        # static India choropleths
python3 deck/make_charts.py      # distribution, weights, validation, business
python3 deck/make_model_figs.py  # clustering + per-axis Monte Carlo
python3 deck/make_diagrams.py    # workflow / framework diagrams
python3 deck/build_deck.py       # -> deck/Trilytics2026_Dhurandar_MAI.pptx
python3 deck/preview.py          # renders the SAVED pptx and flags overflow
```

---

## Full run, one command

`run_all.py` runs the whole model chain in order — build → validate → ml →
benchmarks → narrative → reproduce → G1 (eval, resolve) → G2 (generate, judge)
— freezes the results into `results/<run_id>/`, and then publishes to Firestore.
It streams every step to the terminal and to `logs/run_all_<timestamp>.log`.

```bash
python3 run_all.py             # everything; the Firestore step is a DRY RUN
python3 run_all.py --confirm   # ... and actually write 698 mai_scores + 1 mai_runs
python3 run_all.py --list      # show the steps without running them
```

It keeps three guarantees that matter when the chain is automated rather than typed:

- **Firestore is never written by accident** — `mai.publish` runs without
  `--confirm` unless you pass `--confirm` to `run_all.py`, so the default
  produces every result locally and shows what a publish *would* do.
- **The GenAI steps cannot fail the run** — no Groq key, a 429, or a rejected
  brief degrades to the deterministic templates; only the deterministic steps
  before them are allowed to stop the chain.
- **Nothing is published from a stale build** — `mai.reproduce` runs before
  publish and halts the chain if the inputs have drifted from what the scores
  were built on.

Useful flags: `--skip-genai` (no Groq at all), `--from validate` (resume after a
failure), `--only build,validate,bundle`, `--pull` (refresh the local snapshot
first), `--rpm N` (Groq rate limit, default 12). The `results/latest/RESULTS.md`
it writes is a one-page summary — headline numbers, top district, and every
failing test — with SHA-256s in `MANIFEST.json`.

The deterministic steps take ~30 s end to end; the GenAI steps are paced by the
Groq rate limit, and ingest (§3, run separately) is the genuinely slow part.

### Or step by step

```bash
cp .env.example .env && $EDITOR .env
pip3 install -r requirements.txt

python3 -m pipeline.run --once --force          # ingest + publish sources
python3 analysis/audit/00_pull_firestore.py     # snapshot locally

python3 -m mai.build
python3 -m mai.validate
python3 -m mai.ml
python3 -m mai.benchmarks
python3 -m mai.narrative
python3 -m mai.reproduce --selftest

python3 -m mai.publish                          # inspect the dry run
python3 -m mai.publish --confirm                # write 699 documents
```

## What lands in Firestore

| Collection | Docs | Written by |
|---|---|---|
| `districts/{district_code}` | ~698 | `pipeline.run` (NFHS master profiles) |
| `district_indicators/{district_code}` | ~698 | `pipeline.run` (NFHS-4 + NFHS-5, momentum) |
| `nfhs5_factsheet/{state__district}` | 707 | `pipeline.run` (names only — join via LGD) |
| `secc/{district_code}` | ~631 | `pipeline.run` (SECC 2011 deprivation) |
| `census_pca/{district_code}` | ~728 | `pipeline.run` (population, literacy) |
| `tb_live/{state}` | ~36 | `pipeline.run` (Ni-kshay, hourly) |
| `pmjay_hospitals/{state}` | ~36 | `pipeline.run` (empanelment) |
| `pipeline_status/{source_id}` | 10 | `pipeline.run` (freshness heartbeats) |
| **`mai_scores/{district_code}`** | **698** | **`mai.publish --confirm`** |
| **`mai_runs/{model_version}`** | **1** | **`mai.publish --confirm`** |

Local-only, never published: HMIS (~547k rows), DHS state anchors, SHRUG, and
the geoBoundaries GeoJSON (bundled into `web/public/` instead).

## Repository layout

| Path | What it is |
|---|---|
| `pipeline/` | Fetchers, aggregators, Firestore publisher, daemon |
| `mai/` | The v2 model: features, imputation, index, validation, ML, narratives, publish |
| `mai/genai/` | G1 crosswalk resolution and G2 narratives, with their evaluations |
| `analysis/audit/` | Read-only Firestore snapshot + audit scripts; `_cache/v2/` holds every result |
| `web/` | Next.js dashboard (static export, Firebase Hosting) |
| `deck/` | Figure generators and the submission PPTX builder |
| `docs/` | Case brief, audit findings, uplift plan, changelog, pipeline checklist |
| `notebooks/` | `MAI_analysis.ipynb` — the exploratory v1 analysis the audit was run against |
| `Credentials/` | **Git-ignored** fallback keys |
| `data/`, `logs/` | Raw payloads, pipeline state, run log |

Key documents: [MAI_V2_CHANGELOG.md](docs/MAI_V2_CHANGELOG.md) (what changed and
what still fails), [MAI_AUDIT_FINDINGS.md](docs/MAI_AUDIT_FINDINGS.md),
[MAI_UPLIFT_PLAN.md](docs/MAI_UPLIFT_PLAN.md),
[PIPELINE_CHECKLIST.md](docs/PIPELINE_CHECKLIST.md) (live work-log and known issues),
[DATA_SOURCES_AND_DB_DESIGN.md](docs/DATA_SOURCES_AND_DB_DESIGN.md).

## Troubleshooting

- **`run 'python3 -m mai.validate' first`** — publish needs the rank intervals
  that `validate` writes. Run it.
- **`403 Missing or insufficient permissions`** — the service account lost its
  IAM role; fix steps in [PIPELINE_CHECKLIST.md](docs/PIPELINE_CHECKLIST.md)
  (known issue 7).
- **`QuotaDeferred`** — the daily write budget is spent. Nothing was written;
  rerun after the reset.
- **`another pipeline instance is already running`** — a stale
  `data/state/pipeline.lock`; it releases when that process exits.
- **Staleness FAIL from `mai.reproduce`** — the cache changed after the scores
  were built. Re-run `mai.build` and everything after it before publishing.
- **Groq 429 / daily limit** — add `GROQ_API_KEY_2` to `.env`, or lower `--rpm`.
  The GenAI layer is optional; the templates always publish.
- **Ni-kshay redirect loops / 0 districts** — the site has outages; the daemon
  retries hourly. DNH & Daman & Diu never resolves (known issue 1).
- **Disk** — a full HMIS ingest is ~230 MB gzipped. Keep a few GB free.

## Caveats worth stating up front

Levels are fused across vintages (Census/SECC 2011, NFHS 2019-21, live TB),
which is exactly why the index is built on **rank** normalisation — district
ordering is stable across that span where absolute levels are not. HMIS data
ends ~2021 and its `date` column is malformed. `nfhs5_factsheet` carries
district names only. SHRUG is CC BY-NC-SA (academic use, cite Dev Data Lab).
8 of the 31 validation tests fail; they are reported rather than tuned away —
see the changelog.
