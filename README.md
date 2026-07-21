# Trilytics MAI — District-Level Market Attractiveness Index (Sun Pharma case)

Continuous data pipeline + live Firebase demo for a **District-Level Market
Attractiveness Index** across 700+ Indian districts (student academic project).
The pipeline scrapes free government/academic sources, stores raw data locally,
aggregates to ~700 district documents per source, and upserts them into
**Cloud Firestore** (project `medicine-attractive-index`) that the live demo
app reads.

```
 fetch (A–J sources) ──► data/raw/<source>/ingest_<ts>/   (verbatim, local)
        │
        ▼ aggregate (district level, ~700 docs)
 Cloud Firestore  ◄── batched upserts, daily write budget (Spark free tier)
        ▲
 pipeline_status/* heartbeats — the app shows "last updated X min ago"
```

## Directory layout

| Path | What it is |
|---|---|
| `pipeline/` | The scraping/publishing package (fetchers, aggregators, publisher, daemon) |
| `docs/` | All project documents — see below |
| `Credentials/` | **Git-ignored.** Fallback API keys + service accounts (see [Credentials](#credentials--api-keys)) |
| `data/raw/` | Raw scraped payloads, verbatim, per-ingest timestamped dirs |
| `data/state/pipeline_state.json` | Machine-readable resume state (source of truth) |
| `logs/pipeline.log` | Full run log |
| `.env.example` | Env template — copy to `.env` (auto-loaded; primary secret store) |
| `notebooks/MAI_analysis.ipynb` | Executed analysis: crosswalk → composite MAI → tests → ML → publish |
| `Saved_models/` | Trained models (joblib): 5 proxy-demand, surrogate, k-means |

Documents in `docs/`:
- [PIPELINE_CHECKLIST.md](docs/PIPELINE_CHECKLIST.md) — **live work-log**; STATE table auto-updates after every source run. Start here to resume work.
- [SCRAPING_CHECKLIST.md](docs/SCRAPING_CHECKLIST.md) — source research: what to scrape, what to skip and why.
- [DATA_SOURCES_AND_DB_DESIGN.md](docs/DATA_SOURCES_AND_DB_DESIGN.md) — full source catalog + Firestore schema + app architecture.
- `6a494920656d6_Trilytics_Case_Final.pdf` — the case brief.

## Install

Needs Python ≥ 3.9 (macOS system Python works).

```bash
cd /path/to/Trylitics
pip3 install -r requirements.txt
```

## Credentials / API keys

Credentials are read **from the environment first**, then fall back to the
git-ignored `Credentials/` folder. This means the pipeline runs on **any
machine** with just a `.env` — no local credential files required.

```bash
cp .env.example .env      # then fill in the values
```

`pipeline/config.py` auto-loads `.env` on import (no `source` needed, zero extra
dependencies). Real shell environment variables always override `.env`.

Two credentials are required:

| Credential | `.env` variable | Fallback file | Where to get it |
|---|---|---|---|
| **Firebase Admin SDK key** (required to publish) | `FIREBASE_SERVICE_ACCOUNT_JSON` (whole JSON on one line, single-quoted; or base64) — or a path in `FIREBASE_CREDENTIALS_PATH` | `Credentials/Firebase_Service_Account.json` | [Firebase console](https://console.firebase.google.com/project/medicine-attractive-index/settings/serviceaccounts/adminsdk) → Project settings → Service accounts → *Generate new private key*. Needs the **Firebase Admin SDK Administrator Service Agent** role (or broader) in [IAM](https://console.cloud.google.com/iam-admin/iam?project=medicine-attractive-index). |
| **data.gov.in API key** (source D) | `DATA_GOV_IN_API_KEY` | `Credentials/DATA_GOV_IN_API_KEY.json` → `data_gov_in.api_key` | Free at <https://www.data.gov.in/apis> (one key works platform-wide). |

Optional (unused by the core build, kept for the collaborative Sheets layer):
`GOOGLE_SERVICE_ACCOUNT_JSON` / `GOOGLE_APPLICATION_CREDENTIALS`,
`GOOGLE_SHEET_API_KEY`, `GOOGLE_SHEET_LINK`. See `.env.example` for the full
list and every knob (`PMJAY_STATE_LIMIT`, `FIRESTORE_DAILY_WRITE_CAP`, …).

**No key needed** for: India Data Portal (CKAN), Ni-kshay, PMJAY, geoBoundaries,
DHS. **Deliberately skipped** (org-gated/dead): MoSPI eSankhyiki, NDAP, ABDM,
IDSP — see [SCRAPING_CHECKLIST.md §1](docs/SCRAPING_CHECKLIST.md).
SHRUG (optional) needs a manual table pick — paste zip URLs into
`config.SOURCES['shrug']['download_urls']`.

## Running the scraping workflow

All commands run from the project root.

```bash
python3 -m pipeline.run --status            # where things stand (safe anytime)
python3 -m pipeline.run --once              # run every DUE source once, then exit
python3 -m pipeline.run --once --force      # run everything now, ignore cadence
python3 -m pipeline.run --daemon            # CONTINUOUS mode — the live demo
python3 -m pipeline.run --source nikshay_tb # force specific source(s), comma-separated
python3 -m pipeline.run --once --no-publish # fetch + save raw only, skip Firestore

# test the slow PMJAY scraper on a 2-state subset:
PMJAY_STATE_LIMIT=2 python3 -m pipeline.run --source pmjay_hospitals
```

Source ids: `idp_nfhs` `datagovin_nfhs5` `idp_secc` `geoboundaries`
`nikshay_tb` `idp_pca` `pmjay_hospitals` `idp_hmis` `dhs_state` `shrug`.

**Continuous mode** (`--daemon`) re-checks every 60 s and runs whatever is due:
Ni-kshay TB hourly (the genuinely live source), NFHS/SECC/factsheet/PMJAY
daily, PCA/HMIS/geo/DHS/SHRUG weekly. Unchanged content (sha256) is detected
and not re-published, so idle cycles are cheap. Only one instance can run at a
time (lock file `data/state/pipeline.lock`).

For a demo machine, keep a terminal open with:
```bash
cd /path/to/Trylitics && python3 -m pipeline.run --daemon
```
Stop with `Ctrl-C` (finishes the current source cleanly). If a run dies
mid-way, just rerun — state resumes from `data/state/pipeline_state.json` and
the STATE table in [docs/PIPELINE_CHECKLIST.md](docs/PIPELINE_CHECKLIST.md).

## What lands in Firestore

| Collection | Docs | Source |
|---|---|---|
| `districts/{district_code}` | ~698 | NFHS master profiles |
| `district_indicators/{district_code}` | ~698 | NFHS-4 + NFHS-5 indicators (momentum) |
| `nfhs5_factsheet/{state__district}` | 707 | data.gov.in factsheet (names only — join via LGD) |
| `secc/{district_code}` | ~631 | SECC 2011 deprivation |
| `census_pca/{district_code}` | ~728 | Census PCA population/literacy |
| `tb_live/{state}` | ~36 | Ni-kshay TB, current year, hourly |
| `pmjay_hospitals/{state}` | ~36 | Empanelled hospitals public/private |
| `pipeline_status/{source_id}` | 10 | Heartbeats (freshness for the app) |
| `mai_scores/{district_code}` | 698 | **Final index** — overall/chronic/acute scores, ranks, tiers, rank intervals, clusters |
| `mai_runs/{version}` | 1 | Model reproducibility doc (weights, metrics, method) |

Raw-only (local, not published): HMIS (~547k rows), DHS state anchors,
geoBoundaries GeoJSON (`data/raw/geo/india_adm2.geojson` — bundle into the
app's Hosting `public/`), SHRUG.

## Troubleshooting

- **`403 Missing or insufficient permissions` on publish** — the service
  account lost its IAM role; see the fix steps in
  [docs/PIPELINE_CHECKLIST.md](docs/PIPELINE_CHECKLIST.md) (known issue 7).
- **`another pipeline instance is already running`** — a previous run holds
  `data/state/pipeline.lock`; it releases automatically when that process exits.
- **Ni-kshay redirect loops / 0 districts** — the site has outages; the daemon
  retries hourly. DNH & Daman & Diu never resolves (known issue 1).
- **Disk** — HMIS/PCA pages are gzipped (`.json.gz`); a full HMIS ingest is
  ~230 MB. Keep a few GB free.

## Known caveats (short version)

Full list with details: [docs/PIPELINE_CHECKLIST.md](docs/PIPELINE_CHECKLIST.md#known-issues--honest-caveats).
HMIS data ends ~2021 and its `date` column is malformed (day slot holds the
real month); PCA totals run ~3% under published Census abstracts (source-side);
`nfhs5_factsheet` has district names only; SHRUG is CC BY-NC-SA (academic OK,
cite Dev Data Lab).

## Model (built — see the notebook)

`notebooks/MAI_analysis.ipynb` (executed, outputs embedded) implements
[docs/MAI_MODEL_PLAN.md](docs/MAI_MODEL_PLAN.md): crosswalk → 35-indicator
feature matrix → hypothesis tests → OECD/JRC composite (winsorize → min-max →
pillar weights → arithmetic + geometric) → Monte-Carlo robustness → k-means
segmentation → 5-model proxy-demand validation + MAI surrogate (joblib in
`Saved_models/`) → publishes `mai_scores` + `mai_runs`.

## Next phase (not yet built)

Firebase Hosting demo app reading `mai_scores` (choropleth + rankings +
drill-down) → final deck. Design:
[DATA_SOURCES_AND_DB_DESIGN.md §6](docs/DATA_SOURCES_AND_DB_DESIGN.md).
