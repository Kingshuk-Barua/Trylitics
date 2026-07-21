# PIPELINE CHECKLIST — Trilytics MAI continuous scraping → Firebase

> **RESUMABLE WORK-LOG.** If a session dies, a fresh Claude (or human) reads
> this file and continues from the STATE table below — it is auto-regenerated
> by the pipeline after every source run, from `data/state/pipeline_state.json`
> (the machine-readable source of truth). Predecessor docs:
> [SCRAPING_CHECKLIST.md](SCRAPING_CHECKLIST.md) (source research, §1 skip-list
> still applies) and [DATA_SOURCES_AND_DB_DESIGN.md](DATA_SOURCES_AND_DB_DESIGN.md)
> (architecture §6). Credentials: `Credentials/` (git-ignored).

## What this is
Automated, continuous pipeline: **fetch A–J sources → save raw verbatim to
`data/raw/<source>/ingest_<ts>/` → aggregate to ~700 district docs → upsert to
Cloud Firestore** (project `medicine-attractive-index`) for the live demo app.
Decisions locked with the user 2026-07-15: **Python daemon** (not cron) ·
**aggregates only to Firestore** (raw stays local; Spark ~20k writes/day cap,
budget guard at 15k) · **all sources A–J**.

## How to run
```bash
cd /Users/hrishavmajumder/Documents/Trylitics
python3 -m pipeline.run --status                 # where things stand
python3 -m pipeline.run --once                   # run everything due, then exit
python3 -m pipeline.run --daemon                 # CONTINUOUS mode (the demo)
python3 -m pipeline.run --source nikshay_tb      # force one source
python3 -m pipeline.run --once --no-publish      # fetch only, no Firestore
```
Cadences (config.py): Ni-kshay **hourly** (the live source); NFHS/SECC/factsheet
daily re-verify; PCA/HMIS/geo/DHS/SHRUG weekly; PMJAY daily. Unchanged content
(sha256 match) is detected and NOT re-published — so the daemon idles cheaply.

## Build checklist (code)
- [x] `pipeline/config.py` — source registry, cadences, verify bounds, paths
- [x] `pipeline/state.py` — resumable state + auto-sync of this file
- [x] `pipeline/http_client.py` — retrying session, polite UA
- [x] Fetchers: `idp_ckan` (A/B/C/F) · `datagovin` (D) · `geoboundaries` (E) ·
      `nikshay` (G) · `pmjay` (H) · `shrug` (I) · `dhs` (J)
- [x] `pipeline/transform/aggregate.py` — district-level Firestore payloads
- [x] `pipeline/publish/firestore.py` — batched upserts + daily write budget
- [x] `pipeline/run.py` — --once / --daemon / --source / --status / --no-publish
- [x] Fetch test: every source verified incl. HMIS 547k rows + PMJAY full sweep (39 states / 787 districts). shrug = skipped by design (manual URLs)
- [x] Firestore publish verified 2026-07-16: districts 698 · district_indicators 698 · nfhs5_factsheet 707 · secc 631 · census_pca 728 · pmjay_hospitals 40 · pipeline_status heartbeats. tb_live pending Ni-kshay site recovery (hourly auto-retry)
- [x] Daemon runs verified 2026-07-16: starts clean, holds the instance lock, idles silently when nothing is due, error-backoff active (down sites retried ≤30 min, not every tick). Ni-kshay 2-cycle refresh auto-completes when the site recovers. NOTE: a daemon started from a Claude session dies with that session — for the demo run it in your own terminal: `python3 -m pipeline.run --daemon`
- [x] MAI model executed 2026-07-18 via `notebooks/MAI_analysis.ipynb` (crosswalk 640/687 TB/PMJAY matches → 35-indicator matrix, 3.6% imputed → composite + robustness [top-50 stability 95.2%] → k=3 segmentation → 5-model proxy validation [Lasso, honest R²≈0.11] + surrogate → published 698 `mai_scores` docs + `mai_runs/mai_v1_2026-07-17`; models in `Saved_models/`). Data-quality find: NFHS-4 stores 'not collected' as 0.0 for sugar/BP — treated as missing.
- [ ] Remaining: demo app (Firebase Hosting) → final deck
- [ ] **NFHS-6 (2023-24) released 2026-05-29** — district factsheets for 715
      districts exist as PDFs (nfhsiips.in), but NO machine-readable copy yet:
      IDP's NFHS package still holds only the 2-round resource (verified
      2026-07-17) and data.gov.in has zero NFHS-6 datasets among its 136 NFHS
      entries. When either portal ingests it, add it as a source (would give a
      third momentum point per district); PDF-parsing 715 factsheets is the
      fallback.

## Firestore collections written
| Collection | Docs | Source | Refresh |
|---|---|---|---|
| `districts/{district_code}` | ~700 | idp_nfhs | daily |
| `district_indicators/{district_code}` | ~700 (both NFHS rounds) | idp_nfhs | daily |
| `nfhs5_factsheet/{state__district}` | 707 | datagovin_nfhs5 | daily |
| `secc/{district_code}` | ~640 | idp_secc | daily |
| `census_pca/{district_code}` | ~640 | idp_pca | weekly |
| `tb_live/{state}` (+`_summary`) | ~36 | nikshay_tb | **hourly** |
| `pmjay_hospitals/{state}` (+`_summary`) | ~36 | pmjay_hospitals | daily |
| `pipeline_status/{source_id}` | 10 | every run (heartbeat) | every run |

Raw-only (local, no Firestore): geoBoundaries GeoJSON (stable copy at
`data/raw/geo/india_adm2.geojson` for Hosting `public/`), HMIS (v1), DHS, SHRUG.

## 📌 STATE — auto-generated, do not hand-edit below
<!-- STATE:BEGIN (auto-generated, do not hand-edit) -->

| Step | Source | Status | Rows | Last success | Published docs | Raw path | Notes / error |
|---|---|---|---|---|---|---|---|
| A | `idp_nfhs` | ✅ unchanged | 1267 | 2026-07-20T18:33:01Z | 1396 | /Users/hrishavmajumder/Documents/Trylitics/data/raw/idp_nfhs/ingest_20260715_131243 | unchanged (hash match); total=1267 rows=1267 |
| D | `datagovin_nfhs5` | ✅ unchanged | 707 | 2026-07-20T21:17:23Z | 707 | /Users/hrishavmajumder/Documents/Trylitics/data/raw/datagovin_nfhs5/ingest_20260715_131244 | unchanged (hash match); total=707 |
| C | `idp_secc` | ✅ unchanged | 3786 | 2026-07-20T21:17:26Z | 631 | /Users/hrishavmajumder/Documents/Trylitics/data/raw/idp_secc/ingest_20260715_131246 | unchanged (hash match); total=3786 rows=3786 |
| E | `geoboundaries` | ✅ unchanged | 735 | 2026-07-16T17:01:42Z | — | /Users/hrishavmajumder/Documents/Trylitics/data/raw/geo/ingest_20260715_131625 | unchanged; 735 features |
| G | `nikshay_tb` | ✅ ok | 792 | 2026-07-21T04:55:51Z | 35 | /Users/hrishavmajumder/Documents/Trylitics/data/raw/nikshay/ingest_20260720_211726 | 34 states OK, 792 district rows, 01/01/2026..20/07/2026 / failed: Andhra Pradesh: HTTPSConnectionPool(host='reports.nikshay.in', port=443): Max retries exceeded |
| B | `idp_pca` | ✅ unchanged | 188910 | 2026-07-16T17:01:31Z | 728 | /Users/hrishavmajumder/Documents/Trylitics/data/raw/idp_pca/ingest_20260715_131856 | unchanged (hash match); total=188910 rows=188910 |
| H | `pmjay_hospitals` | ✅ unchanged | 787 | 2026-07-21T06:03:46Z | 40 | /Users/hrishavmajumder/Documents/Trylitics/data/raw/pmjay/ingest_20260721_045552 | 39 states, 787 districts; public/private counts parsed |
| F | `idp_hmis` | ✅ ok | 547336 | 2026-07-16T16:58:17Z | — | /Users/hrishavmajumder/Documents/Trylitics/data/raw/idp_hmis/ingest_20260716_165817 | total=547336, fetched 547336 rows in 110 pages; expected (500000, 600000) OK |
| J | `dhs_state` | ✅ ok | 144865 | 2026-07-16T17:04:48Z | — | /Users/hrishavmajumder/Documents/Trylitics/data/raw/dhs/ingest_20260716_170446 | 144865 rows across 29 page(s); STATE-level anchor only |
| I | `shrug` | ⏭ skipped | — | — | — | — | manual step: pick tables at https://www.devdatalab.org/shrug_download/ and paste the direct zip URLs into config.SOURCES['shrug']['download_urls'] |

_Firestore writes today (2026-07-21): 37 / 15000 cap._
_Table auto-updated 2026-07-21T06:04:46Z._

<!-- STATE:END -->

## Known issues / honest caveats
1. **Ni-kshay 'Dadra & Nagar Haveli & Daman & Diu'** — no tested spelling is
   accepted (0 districts). Both legacy names stay in the state list so the
   failure remains visible in `tb_live/_summary.states_failed`. TODO: sniff the
   exact name from the site's own XHR when convenient.
2. **PMJAY full run is slow** (~740 districts × paginated POSTs, ~30–60 min)
   and the site can rate-limit; per-district failures are recorded, not hidden.
   Test with `PMJAY_STATE_LIMIT=2 python3 -m pipeline.run --source pmjay_hospitals`.
3. **HMIS (F)**: raw-only in v1. Data ends ~2021; `date` column malformed —
   month always `01`, the **day slot holds the real month**. Parse as
   year + day-as-month when building the interim layer. ~547k rows ≈ large pull.
4. **SHRUG (I)**: needs a human to pick tables (license CC BY-NC-SA, academic
   OK). Paste direct zip URLs into `config.SOURCES['shrug']['download_urls']`;
   until then the step self-reports `skipped`.
5. **data.gov.in factsheet (D)** has district **names only** — join via the LGD
   crosswalk (design doc §6.2); the IDP copy (A) carries `district_code`.
6. **PCA aggregation** keeps only unambiguous cuts (pure population, literacy,
   age 0–6) — see `PcaAgg` docstring. Everything else stays raw-only until the
   interim layer.
7. **✅ RESOLVED (2026-07-16): Firestore publish.** Was blocked by missing
   IAM bindings on the Admin SDK service account; user regenerated the key
   and granted Owner (works; can be narrowed to *Firebase Admin SDK
   Administrator Service Agent* later). Also fixed en route: batch commits
   are now size-adaptive (SECC docs blew the 10MB commit limit), and
   nfhs5_factsheet doc ids are `state__district` (the real payload keys are
   `State_UT`/`District_Names`; 8 districts repeat names across states —
   699 wrongly-keyed `na_*` docs were deleted from Firestore).

## Resume prompt (paste into a fresh Claude session)
```
Read docs/PIPELINE_CHECKLIST.md in /Users/hrishavmajumder/Documents/Trylitics.
Run `python3 -m pipeline.run --status`, compare with the STATE table, and
continue from the first unchecked build-checklist item / first error row.
Do not re-plan. Never fake data; record exact errors in the state table.
```
