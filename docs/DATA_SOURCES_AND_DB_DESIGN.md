# Trilytics 2026 (Sun Pharma) — District-Level Market Attractiveness Index
## Data Sources Catalog + Database Design

> **Case:** Build a statistical framework that generates **District-Level Market (Pharmaceutical) Attractiveness Index** scores for **700+ Indian districts**, producing **three** scores per district:
> 1. **Overall** Market Attractiveness Index
> 2. **Chronic** Therapy Market Attractiveness Index
> 3. **Acute** Therapy Market Attractiveness Index
>
> The model must integrate: macroeconomics, disease prevalence/epidemiology, patient pool & patient-to-doctor ratio, provider/doctor density, healthcare infrastructure & access, healthcare spending & affordability, and forward-looking/leading indicators (income growth, urbanization, risk-factor trends).
>
> **This document** lists **free / open-source, authentic (Government-of-India-preferred), district-level** data sources — how to fetch each (scrape / API / download), which URLs and API keys are needed — and then a **database design** built on the resources present in `Credentials/` (Firebase + Google Cloud + Google Sheets).
>
> _Compiled: 2026-07-14. All sources verified reachable by research agents on this date._

---

## Table of Contents
1. [How to read this document](#1-how-to-read-this-document)
2. [Variable → Source → Index mapping (the blueprint)](#2-variable--source--index-mapping-the-blueprint)
3. [Consolidated credentials & environment keys](#3-consolidated-credentials--environment-keys)
4. [Data Sources Catalog](#4-data-sources-catalog)
   - [4.1 Demographics, Census & Macroeconomic](#41-demographics-census--macroeconomic)
   - [4.2 Disease Epidemiology (Chronic & Acute)](#42-disease-epidemiology-chronic--acute)
   - [4.3 Healthcare Infrastructure, Providers & Access](#43-healthcare-infrastructure-providers--access)
   - [4.4 Healthcare Spending, Affordability, Insurance & Pharma Market](#44-healthcare-spending-affordability-insurance--pharma-market)
   - [4.5 GIS / District Boundaries (for maps & heatmaps)](#45-gis--district-boundaries-for-maps--heatmaps)
   - [4.6 Paid commercial pharma-sales (reference only — NOT used)](#46-paid-commercial-pharma-sales-reference-only--not-used)
5. [Access recipes (scrape / API / download)](#5-access-recipes-scrape--api--download)
6. [Database Design](#6-database-design)
7. [Data gaps & proxy strategy](#7-data-gaps--proxy-strategy)
8. [Recommended build sequence](#8-recommended-build-sequence)

---

## 1. How to read this document

- **Preference order for acquisition:** (1) **API** → (2) **bulk file download** (CSV/XLSX) → (3) **web scraping of portals/dashboards** → (4) **PDF table extraction** (Tabula/Camelot). "Scrape (preferred)" from the brief is honoured wherever a portal exposes JSON/AJAX; otherwise the cleanest machine-readable route is named.
- **Authenticity flag:** 🟢 = official Government of India / statutory body · 🔵 = reputed academic/multilateral (WHO, IHME, World Bank, university labs) · 🟡 = community/open (GitHub mirrors, OSM, DataMeet) · 🔴 = commercial/paid (documented for context, **not** used).
- **Everything marked FREE is genuinely free.** The only recurring credential to provision is a free **data.gov.in API key**. A handful of portals need a free login (MoSPI microdata, DHS, IHME).
- **Granularity honesty:** the brief needs **district** data. Where a strong source is only **state**-level (GBD, ICMR-INDIAB, NHA, IRDAI, NPPA), it is flagged and a **downscaling/proxy** strategy is given in §7.

---

## 2. Variable → Source → Index mapping (the blueprint)

This is the spine of the model — each candidate variable, its primary free district source, and which of the three indices it feeds. **C** = Chronic, **A** = Acute, **O** = Overall (all three share the Overall base). Direction: **(+)** raises attractiveness, **(−)** lowers it.

| Pillar | Variable | Primary free source (district) | Index | Dir |
|---|---|---|---|---|
| **Macro / Market size** | Population, density, urban % | Census 2011 PCA / NFHS-5 | O·C·A | + |
| | Decadal growth, projected pop. | Census 2011 + derived projections | O (leading) | + |
| | Per-capita income / DDP | State DES District Domestic Product; SHRUG consumption proxy | O·C·A | + |
| | Wealth / asset index | NFHS-5 wealth index; SECC 2011 | O·C·A | + |
| | Poverty (MPI) | NITI Aayog National MPI (707 dist.) | O | − |
| | Urbanization/income momentum | SHRUG night-lights growth; NFHS-4→5 delta | O (leading) | + |
| **Chronic disease burden** | Diabetes / high blood glucose | NFHS-5 (district) + ICMR-INDIAB (state anchor) | **C** | + |
| | Hypertension / high BP | NFHS-5 (district) | **C** | + |
| | Overweight/obesity (BMI) | NFHS-5 (district) | **C** | + |
| | CVD / IHD / stroke, CKD, COPD | IHME GBD (state → downscaled) | **C** | + |
| | Cancer incidence | NCRP/NCDIR (registry) + GBD | **C** | + |
| | Tobacco / alcohol (risk) | NFHS-5 (district) | **C** (leading) | + |
| **Acute disease burden** | Malaria / dengue / chikungunya | EpiClim / IDSP / NCVBDC (district) | **A** | + |
| | Acute diarrhoeal, cholera, typhoid | EpiClim / IDSP; HMIS | **A** | + |
| | ARI / childhood fever / infections | NFHS-5; HMIS | **A** | + |
| | TB notifications | Ni-kshay (district/TU) | **A** | + |
| | Anaemia, maternal & child health | NFHS-5 (district) | **A** | + |
| | Immunization coverage | NFHS-5; HMIS | **A** | + |
| **Provider availability** | Doctors, specialists, patient-to-doctor ratio | RHS/"Health Dynamics of India" + NHP + NMR/NHPR | O (specialists → C) | + |
| | Nurses, pharmacists | NHP; NHPR | O | + |
| **Infrastructure & access** | PHC/CHC/SC/DH counts, beds/capita | RHS 2022-23 (district) + data.gov.in | O | + |
| | Infrastructure shortfall vs norms | RHS (district) | O | − |
| | Private hospitals & specialties | PMJAY empanelled hospitals (HEM) + HFR | O (specialties → C) | + |
| | Pharmacy / chemist density | HFR pharmacies + OSM Overpass; Jan Aushadhi kendras | O | + |
| | Primary-care / NCD-screening reach | AB-HWC / Ayushman Arogya Mandir | O (screening → C) | + |
| | Diagnostic labs / imaging | HFR (district) | O·C | + |
| **Spending & affordability** | OOP & per-capita health spend | NHA (national/state) → apportioned | O | + |
| | Household medical MPCE | HCES 2022-23; NSS 75th (state → district codes) | O (hosp.→A; non-hosp.→C) | + |
| | Health-insurance coverage | NFHS-5 (district) + PMJAY cards (district) | O | + |
| | PMJAY claims / utilization | PMJAY Insights dashboard (district) | O·A | + |
| | Generic-medicine access | Jan Aushadhi kendra density (district) | O·C | + |
| | Drug price benchmarks | NPPA ceiling prices (national) | O·C·A | context |
| **Leading / forward-looking** | Income growth, urbanization trend | SHRUG night-lights; Census growth; NFHS deltas | O (future) | + |
| | Risk-factor trajectory | NFHS-4→5 change in BMI/BP/glucose/tobacco | **C** (future) | + |
| | Infra momentum | AB-HWC rollout; HFR onboarding growth | O (future) | + |

> **Chronic vs Acute differentiation logic:** the **Chronic** index over-weights NCD prevalence (diabetes/BP/BMI/cancer/CVD), specialist & diagnostic availability, generic/maintenance-medicine access (Jan Aushadhi), and NCD-risk trajectory. The **Acute** index over-weights infectious/seasonal burden (EpiClim/IDSP/NCVBDC/TB), childhood/maternal indicators, hospitalization-based medical spend, and PMJAY secondary/tertiary claims. The **Overall** index blends both plus the shared macro / access / affordability base.

---

## 3. Consolidated credentials & environment keys

### 3.1 Keys you must create (free)

| Env variable (suggested) | Used by | How to get it | Cost |
|---|---|---|---|
| `DATA_GOV_IN_API_KEY` | data.gov.in REST API (Census PCA, NFHS-5, RHS health-centres, AB-HWC, AYUSH, malaria, etc.) | Register at [data.gov.in](https://www.data.gov.in) → **My Account → Generate API Key** (40-char key). `DEMO_KEY`/public sample key works for testing but is rate-limited. | Free |
| *(interactive login)* | **MoSPI microdata** (HCES, NSS 75th) | Free account at [microdata.gov.in](https://microdata.gov.in/NADA/) | Free |
| *(interactive login)* | **IHME GBD Results Tool** | Free account at [vizhub.healthdata.org/gbd-results](https://vizhub.healthdata.org/gbd-results/) | Free |
| *(interactive login)* | **DHS Program** (NFHS unit-level microdata) | Free registration/approval at [dhsprogram.com](https://dhsprogram.com) | Free |
| *(optional)* `ABDM_CLIENT_ID` / `ABDM_CLIENT_SECRET` | HFR/NHPR **gateway APIs** (only if you use APIs instead of scraping the public portals) | ABDM sandbox onboarding at [sandbox.abdm.gov.in](https://sandbox.abdm.gov.in/) | Free |

> **Note:** the `datagovindia` Python wrapper reads the key from env var **`DATAGOVINDIA_API_KEY`** by convention — set both names to the same value to be safe.

### 3.2 Credentials already provisioned (in `Credentials/`)

> ⚠️ **These files contain private keys — keep them out of version control (`.gitignore` the `Credentials/` folder) and never paste their contents into shared documents.** Load them via env vars / `GOOGLE_APPLICATION_CREDENTIALS` at runtime.

| File | Type | Project | Grants access to |
|---|---|---|---|
| `Firebase_Service_Account.json` | Firebase Admin service account | `medicine-attractive-index` | **Cloud Firestore** (NoSQL serving DB), **Firebase Cloud Storage** (raw data lake), Firebase Auth (for a dashboard) |
| `Google_Service_Account_Credentials.json` | GCP service account (`medicine-atractive-index@sodium-primer-502411-i9…`) | `sodium-primer-502411-i9` | **Google Sheets API**, **Google Drive API**, optionally **BigQuery** (if enabled on that project) |
| `Google_Sheet_Api.json` | Google API key (`AIza…CnBs`) | — | Read-only Google Sheets access (public sheets), Google Maps/geocoding if enabled |
| `Google_Sheet_link.json` | Spreadsheet URL (`…/1b2Pvp8j9KENmVeONJ-kC56WU9iYLUwMRU2EnEXXkc4g`) | — | The working Google Sheet used as staging / collaboration layer |

**Runtime env setup (example):**
```bash
export DATA_GOV_IN_API_KEY="<your 40-char key>"
export DATAGOVINDIA_API_KEY="$DATA_GOV_IN_API_KEY"
export FIREBASE_CREDENTIALS="Credentials/Firebase_Service_Account.json"                        # PRIMARY — Firestore/Storage/Hosting
# --- optional (only if you use the Google Sheet curation grid, §6.7) ---
export GOOGLE_APPLICATION_CREDENTIALS="Credentials/Google_Service_Account_Credentials.json"    # Sheets/BigQuery
export GSHEET_ID="1b2Pvp8j9KENmVeONJ-kC56WU9iYLUwMRU2EnEXXkc4g"
```
The **Firebase** service account (`firebase-adminsdk-fbsvc@medicine-attractive-index…`) already has write access to its own project's Firestore/Storage — no extra sharing needed. Only if you use the optional Sheet, share it as *Editor* with `medicine-atractive-index@sodium-primer-502411-i9.iam.gserviceaccount.com`.

---

## 4. Data Sources Catalog

Legend: **Access** = preferred acquisition method · **Key** = credential required · all sources **FREE** unless in §4.6.

### 4.1 Demographics, Census & Macroeconomic

| # | Source | Auth | Granularity | Access | Key |
|---|---|---|---|---|---|
| D1 | Census of India 2011 (PCA, HH tables, District Handbooks) | 🟢 RGI/MHA | District (640) → village | Bulk XLSX/PDF download | none |
| D2 | data.gov.in (OGD Platform) | 🟢 MeitY/NIC | District (dataset-dep.) | REST API + CSV/XLSX | `DATA_GOV_IN_API_KEY` |
| D3 | NITI Aayog National MPI | 🟢 NITI Aayog | District (707) | PDF annexure tables | none |
| D4 | NITI for States (NFS) Data Catalogue | 🟢 NITI Aayog | District | Portal download (free login) | login |
| D5 | District Domestic Product (State DES) | 🟢 MoSPI + State DES | District (26 states) | PDF/XLSX per state | none |
| D6 | RBI Handbook of Statistics on Indian States | 🟢 RBI | **State only** | XLSX/PDF + DBIE | none |
| D7 | SHRUG (Development Data Lab) | 🔵 academic | Village/town → District | Bulk download (free reg.) | login |
| D8 | SECC 2011 | 🟢 MoRD | District → block | Portal download | none |
| D9 | IHME GBD (subnational) | 🔵 IHME | State (district for select outcomes) | Results tool → CSV (free login) | login |

**D1 — Census of India 2011** 🟢 (primary district demographic spine; vintage 2011 as 2021 census delayed)
- Landing: `https://censusindia.gov.in/census.website/en/data`
- Census Tables (bulk XLSX): `https://censusindia.gov.in/census.website/data/census-tables`
- District Census Handbooks (PDF/district): `https://censusindia.gov.in/census.website/data/handbooks`
- Population Finder: `https://censusindia.gov.in/census.website/data/population-finder`
- NADA catalog (PCA): `https://censusindia.gov.in/nada/index.php/catalog/6191`
- **Access:** scripted XLSX downloads (no live REST API — the advertised `/data/api/documentation` path is a 404). Primary Census Abstract has ~85 district indicators.
- **Variables:** population, density, urban %, decadal growth, age/sex/literacy, household amenities, electrification, banking access. **Format:** XLSX/PDF. **Cost:** Free.

**D2 — data.gov.in (OGD Platform)** 🟢 (programmatic layer — **address data by resource-id, not `/catalog/` slugs**; see §5A for verified ids + discovery)
- Portal: `https://www.data.gov.in` · API host: `https://api.data.gov.in`
- **Discovery:** `GET https://api.data.gov.in/lists?api-key=<KEY>&format=json&filters[title]=<phrase>` (the `filters[title]` substring filter is what works; `query=` is ignored).
- **Pull:** `GET https://api.data.gov.in/resource/<resource-id>?api-key=<KEY>&format=json&limit=1000&offset=0` (also `format=csv`).
- **What's genuinely district-level here:** NFHS-5 district factsheets (`cf80173e-…`, 707), district-wise health centres (`6t201darmc8ocx5p06s9db1ycd86afce`, 707), PCA 2011 (per-state, district rows). Ayushman/HMIS/AYUSH tables are **state-level** on data.gov.in — get district granularity from their primary portals.
- **Key:** `DATA_GOV_IN_API_KEY` (free). **Format:** JSON/CSV. **Cost:** Free.

**D3 — NITI Aayog National MPI** 🟢 (district poverty; 707 districts; built on NFHS)
- Baseline 2021: `https://www.niti.gov.in/sites/default/files/2021-11/National_MPI_India-11242021.pdf`
- Progress Review 2023: `https://www.niti.gov.in/sites/default/files/2024-01/MPI-22_NITI-Aayog20254.pdf`
- OPHI mirror/methodology: `https://ophi.org.uk/national-mpi-directory/india-mpi`
- **Access:** district MPI headcount/intensity in PDF annexure tables (Tabula/Camelot). **Cost:** Free.

**D4 — NITI for States (NFS) Data Catalogue** 🟢 (newer NITI portal aggregating district datasets across sectors)
- `https://www.nitiforstates.gov.in/data-catalogue` — free login. **Cost:** Free.

**D5 — District Domestic Product (State DES)** 🟢 (ideal district income variable; coverage gap — only ~26 states compile, methodologies vary)
- MoSPI Regional Accounts: `https://mospi.gov.in/137-regional-accounts` + individual State Directorate of Economics & Statistics sites. New uniform DDP guideline (base 2022-23) issued 2025. **Where missing → substitute SHRUG (D7) / NFHS wealth.**

**D6 — RBI Handbook of Statistics on Indian States** 🟢 (**state-level only** — use as normalizer/benchmark)
- `https://www.rbi.org.in/scripts/AnnualPublications.aspx?head=Handbook+of+Statistics+on+Indian+States`; DBIE `https://data.rbi.org.in/DBIE/`. State per-capita NSDP, banking/credit-deposit ratios.

**D7 — SHRUG (Development Data Lab)** 🔵 (village/town → district; consumption/income proxy, night-lights growth = economic momentum)
- `https://www.devdatalab.org/shrug` — free registration; CSV/Stata/shapefile. Built on SECC 2011 + Economic Census + night-lights. **Best fill for the district-income gap.**

**D8 — SECC 2011** 🟢 (district → block deprivation/income-band proxy; underlies PMJAY targeting) — `https://secc.gov.in/`

**D9 — IHME GBD** 🔵 (India resolves to **state**; district only for select outcomes — downscale) — `https://vizhub.healthdata.org/gbd-results/`, GHDx `https://ghdx.healthdata.org/ihme_data`. Free login. *(Also a disease source — see §4.2.)*

> **Population projections gap:** no official district-level projection exists (National Commission on Population publishes **state**-level 2011–2036 only). Derive district projections = 2011 district base × state growth rate, or use WorldPop gridded population; use SHRUG night-lights growth + NFHS-4→5 deltas as district momentum proxies.

---

### 4.2 Disease Epidemiology (Chronic & Acute)

> **The most decisive domain for splitting Chronic vs Acute.** Workhorses with true 700+ district coverage: **NFHS-5** (survey prevalence) and **HMIS** (service/incidence). **EpiClim** is the standout for acute district-week infectious data. GBD / INDIAB / NCRP are excellent but **state/registry**-level → downscale.

| # | Source | Auth | Chronic/Acute | Granularity | Access | Key |
|---|---|---|---|---|---|---|
| H1 | **NFHS-5 / NFHS-4 District Fact Sheets** | 🟢 IIPS/MoHFW | **Both** (strongest single) | District (707 / 640) | Compendium XLSX + PDF; GitHub CSV mirrors | none |
| H2 | NFHS-5 on data.gov.in | 🟢 NIC | Both | District | REST API | `DATA_GOV_IN_API_KEY` |
| H3 | **HMIS** (Health Mgmt Info System) | 🟢 MoHFW | Both | District + sub-district | Standard Reports (XLSX/HTML) + data.gov.in | portal: none |
| H4 | IHME **GBD** Results Tool + GHDx | 🔵 IHME | Both | State (district: select) | Web tool → CSV | free login |
| H5 | **IDSP** Weekly Outbreaks | 🟢 NCDC/MoHFW | **Acute** | District (outbreak) | Per-week PDFs (parse) | none |
| H6 | **EpiClim** (cleaned IDSP) | 🟡 academic | **Acute** | District, weekly, 2009→ | Bulk CSV (GitHub) | none |
| H7 | **NCRP / NCDIR** (cancer) | 🟢 ICMR | **Chronic** | 36 registries (not all dist.) | PDF reports + annexures | none |
| H8 | **NCVBDC / NVBDCP** | 🟢 MoHFW | **Acute** | Malaria: district (partial) | PDF + data.gov.in | none |
| H9 | **Ni-kshay** + India TB Report | 🟢 Central TB Div | **Acute** | District / TU | Dashboard export + PDF | none |
| H10 | **ICMR-INDIAB** | 🟢 ICMR | **Chronic** | **State (31)** | Journal + exec-summary PDF | none |
| H11 | NNMS (NCD Monitoring Survey) | 🟢 ICMR-NCDIR | Chronic (risk) | National/regional | PDF factsheet | none |

**H1 — NFHS-5 / NFHS-4 District Fact Sheets** 🟢 (**primary district health source**; NFHS-5 = all **707 districts**, 2019-21; NFHS-4 = 640, 2015-16 → use delta as momentum)
- Fact-sheet index: `http://rchiips.org/nfhs/districtfactsheet_NFHS-5.shtml`
- **Consolidated compendium (bulk, key link):** `http://rchiips.org/nfhs/Factsheet_Compendium_NFHS-5.shtml`
- DHS compendium PDF: `https://dhsprogram.com/pubs/pdf/OF43/NFHS-5_India_and_State_Factsheet_Compendium_Phase-II.pdf`
- **Model-ready CSV mirrors (recommended):** `https://github.com/pratapvardhan/NFHS-5` (Harvard Dataverse `doi.org/10.7910/DVN/42WNZF`; note district file partial ~341 dist.), `https://github.com/SaiSiddhardhaKalla/NFHS` (NFHS-4 **and** 5, district-wise), `https://data.mendeley.com/datasets/t3s358sfzg/1`.
- Unit-level microdata (custom district tabulation): World Bank `https://microdata.worldbank.org/index.php/catalog/4482` / DHS (free reg.).
- **Chronic variables:** high blood glucose (>140/>160 mg/dl), hypertension (elevated BP; on medication), BMI overweight/obese, tobacco, alcohol *(blood-sugar & BP newly added at district level in NFHS-5 — major win)*. **Acute variables:** anaemia, full immunization, ANC/institutional delivery, childhood ARI/fever/diarrhoea, IMR/U5MR, sanitation/clean fuel. **Overall:** health-insurance coverage, wealth index. **Format:** XLSX/PDF/CSV. **Cost:** Free.

**H2 — NFHS-5 district factsheets on data.gov.in** 🟢 **✅ VERIFIED — the single best API-accessible district source.** Resource-id `cf80173e-fece-439d-a0b1-6e9cb510593d` → **707 districts × 109 indicators** (IIPS), and it carries the **full** factsheet (NOT a reduced subset): blood sugar (women/men high & very-high, on-medication), elevated BP (mild/moderate), BMI/overweight/obese, women's breast/cervical/oral cancer, tobacco & alcohol (chronic); diarrhoea/ORS/zinc, ARI, immunization, anaemia (acute); plus health-insurance coverage, out-of-pocket expenditure, electricity/sanitation. Pull via §5A. `DATA_GOV_IN_API_KEY`. This alone can seed most of the Chronic and Acute indices.

**H3 — HMIS** 🟢 (best **service/incidence** panel; district + sub-district, monthly, since 2008-09)
- Portal: `https://hmis.mohfw.gov.in/` → Report → **Standard Reports** → "Data Item-wise Monthly (up to sub-district)" → *All States Across Districts*.
- data.gov.in has **Item-wise HMIS reports per state/year** (verified titles like "Item-wise HMIS report of Maharashtra for 2018-19", ids via `filters[title]=HMIS`) — these are largely state/year aggregates, so for true **district/sub-district** data use the portal Standard Reports above. GHDx series: `https://ghdx.healthdata.org/series/india-health-management-information-system-hmis`.
- **Chronic:** NP-NCD screening — diabetes/hypertension/oral-breast-cervical cancer screened & diagnosed. **Acute:** malaria/dengue/fever/ARI/diarrhoea treated, immunization doses, ANC, institutional deliveries. **Overall:** OPD/IPD footfall, service availability. *(Reflects reporting/access, not pure prevalence — normalize by population.)* **Format:** XLSX/HTML/CSV. **Cost:** Free.

**H4 — IHME GBD Results Tool + GHDx** 🔵 (both indices; **India = state level**, ~31 states; district only for select LBD outcomes — downscale via NFHS/HMIS)
- `https://vizhub.healthdata.org/gbd-results/`; India initiative `https://www.healthdata.org/disease-burden-initiative-india`; GBD Compare `https://vizhub.healthdata.org/gbd-compare/india`.
- **Variables:** DALYs/prevalence/incidence — diabetes, IHD/stroke, CKD, COPD/asthma, cancers, mental health (**chronic**); LRI, diarrhoeal, malaria, dengue, TB, maternal/neonatal (**acute**); 88 risk factors. GBD 2021/2023. Free login → CSV. **Cost:** Free.

**H5 — IDSP Weekly Outbreaks** 🟢 (**acute** early-warning; one PDF per epi-week → parse; cleaner mirrors below)
- `https://idsp.mohfw.gov.in/` → Weekly Outbreaks (`index4.php?lang=1&level=0&linkid=406&lid=3689`); GHDx series `https://ghdx.healthdata.org/series/india-integrated-disease-surveillance-programme-idsp-weekly-outbreaks`; cleaned mirror `https://dataful.in/datasets/18514/`.
- **Variables:** outbreak cases/deaths — acute diarrhoeal, dengue, malaria, chikungunya, cholera, typhoid, measles, hepatitis A/E, ARI/influenza, food poisoning, leptospirosis. **Cost:** Free.

**H6 — EpiClim (cleaned IDSP)** 🟡 **HIGH VALUE** (turns IDSP PDFs into an analysis-ready **district-week** panel, 2009→present)
- Paper + repo: `https://arxiv.org/html/2501.18602v1` (links GitHub CSV). **Variables (acute):** ADD (~59%), dengue, cholera, malaria, chikungunya + climate covariates (temp, precip, LAI) + lat/long for seasonality features. **Cost:** Free (check repo license for commercial use).

**H7 — NCRP / NCDIR (cancer)** 🟢 (**chronic**; 36 population-based registries — NOT all 707 districts → anchor + interpolate)
- Report 2020: `https://ncdirindia.org/All_Reports/Report_2020/default.aspx`; PBCR annexures: `https://ncdirindia.org/All_Reports/PBCR_Annexures/Default.aspx`; full PDF: `https://www.ncdirindia.org/All_Reports/Report_2020/resources/NCRP_2020_2012_16.pdf`; microdata (request) `https://data.icmr.org.in/`.
- **Variables:** cancer incidence (AAR/crude) by site/sex/registry. Covers 2012-16; projected to 2025. **Cost:** Free.

**H8 — NCVBDC / NVBDCP** 🟢 (**acute** vector-borne; malaria district-wise in reports, dengue/chik mostly state → cross-fill from EpiClim/HMIS)
- `https://ncvbdc.mohfw.gov.in/`; keyword feed `https://www.data.gov.in/keywords/Malaria`. Malaria (Pf/Pv) cases/deaths/API, dengue, chikungunya, JE/AES, kala-azar, LF. **Cost:** Free.

**H9 — Ni-kshay + India TB Report** 🟢 (**acute/infectious**; district/TU via Ni-kshay)
- Ni-kshay dashboard: `https://reports.nikshay.in/reports/tbnotification`; TB Report 2024 PDF: `https://tbcindia.mohfw.gov.in/wp-content/uploads/2024/10/TB-Report_for-Web_08_10-2024-1.pdf`; data.gov.in (state) `.../stateut-wise-number-tuberculosis-tb-cases-notification…`. TB notifications (public/private), rate/100k, outcomes, DR-TB. **Cost:** Free.

**H10 — ICMR-INDIAB** 🟢 (**chronic** gold-standard; **state-level (31)** — state calibration layer, downscale via NFHS)
- Lancet 2023: `https://www.thelancet.com/journals/landia/article/PIIS2213-8587(23)00119-5/fulltext`; exec summary `https://www.icmr.gov.in/icmrobject/static/icmr/dist/images/pdf/reports/Executive_summary_INDIAB_Phase_I.pdf`. Diabetes 11.4%, prediabetes 15.3%, hypertension 35.5%, obesity, dyslipidaemia. **Cost:** Free.

**H11 — NNMS** 🟢 (chronic risk factors; **national/regional** — supplementary calibration) — `https://www.ncdirindia.org/nnms/resources/factsheet.pdf` (2017-18). Tobacco, alcohol, physical activity, salt, raised BP/glucose, overweight.

---

### 4.3 Healthcare Infrastructure, Providers & Access

| # | Source | Auth | Granularity | Access | Key |
|---|---|---|---|---|---|
| I1 | **RHS / "Health Dynamics of India" 2022-23** | 🟢 MoHFW | **District** | PDF+XLSX tables (+ data.gov.in) | none |
| I2 | data.gov.in — District-Wise Health Centres | 🟢 NIC | **District** | REST API + bulk | `DATA_GOV_IN_API_KEY` |
| I3 | National Health Profile (NHP) | 🟢 CBHI/DGHS | Mostly State | PDF + e-book | none |
| I4 | HMIS Standard Reports | 🟢 MoHFW | **District & sub-district** | Portal reports + API | portal: none |
| I5 | **Health Facility Registry (HFR/ABDM)** | 🟢 NHA | **District** (filter) | Portal scrape + gateway API | portal: none |
| I6 | Healthcare Providers Registry (NHPR/HPR) | 🟢 NHA | District (address) | Portal scrape + API | portal: none |
| I7 | **PMJAY Empanelled Hospitals (HEM)** | 🟢 NHA | **District** (filter) | Portal scrape + PDF | none |
| I8 | AB-HWC / Ayushman Arogya Mandir | 🟢 MoHFW/NHSRC | **District** | Portal dashboards + PDF | none |
| I9 | Indian/National Medical Register (IMR/NMR) | 🟢 NMC | State (address→district) | Search portal scrape | none |
| I10 | Pharmacy Council of India + CDSCO | 🟢 PCI/CDSCO | State (weak district) | Dashboard + PDF | none |
| I11 | AYUSH datasets (NAM) | 🟢 Min. AYUSH | State; some district | data.gov.in API + portal | `DATA_GOV_IN_API_KEY` |
| I12 | **OpenStreetMap (Overpass)** | 🟡 OSM | Point → any district | Overpass API | none |
| I13 | Google Places API | 🔴 Google | Point | API | `GOOGLE_MAPS_API_KEY` (**PAID**) |

**I1 — Rural Health Statistics / "Health Dynamics of India (Infrastructure & HR) 2022-23"** 🟢 (**core district infrastructure source**, as of 31 Mar 2023)
- Reports landing: `https://www.mohfw.gov.in/?q=reports-23`; direct PDF: `https://hmis.mohfw.gov.in/downloadfile?filepath=publications/Rural-Health-Statistics/RHS+2022-23.pdf` *(transient 500 seen — retry)*; press: `https://pib.gov.in/PressReleasePage.aspx?PRID=2053070`.
- **Variables (district-wise annexures):** SC/PHC/CHC/SDH/DH/medical-college counts, rural/urban/tribal splits, **doctors/specialists/nurses/paramedics**, and **infrastructure shortfall vs IPHS/population norms**. Extract PDF tables via Tabula/Camelot. **Cost:** Free.

**I2 — "district wise health centres" on data.gov.in** 🟢 **✅ VERIFIED.** Resource-id `6t201darmc8ocx5p06s9db1ycd86afce` → **707 districts**, columns = State / District / #Sub-Centres / #PHCs / #CHCs / #Sub-Divisional Hospital / #District Hospital (delivered as one tab-separated string field — split on `\t` after fetch). Pull via §5A. `DATA_GOV_IN_API_KEY`. For manpower (doctors/specialists/nurses) and shortfall-vs-norms, use the RHS PDF (I1) — those aren't in this resource. **Cost:** Free.

**I3 — National Health Profile (NHP 2022)** 🟢 (**state-level** provider-registration counts) — landing `http://cbhidghs.mohfw.gov.in/publications/national-health-profile`; PDF `http://cbhidghs.mohfw.gov.in/sites/default/files/2024-09/national-health-profile-2022.pdf`. Registered doctors/nurses/pharmacists/dentists/AYUSH, blood banks. **Cost:** Free.

**I4 — HMIS Standard Reports** 🟢 (district & sub-district infra items: manpower, equipment, service availability incl. super-specialty/cardiology → chronic signal) — `https://hmis.mohfw.gov.in/`; data.gov.in mirror `.../item-wise-hmis-report-all-states-and-districts-across-months`. **Cost:** Free.

**I5 — Health Facility Registry (HFR / ABDM)** 🟢 (best **private** facilities/labs/imaging/pharmacies with Facility ID; district filter)
- Public search: `https://facility.abdm.gov.in/searchV2` (filter system-of-medicine, facility type, state, **district**). Gateway REST APIs via ABDM sandbox `https://sandbox.abdm.gov.in/` (OAuth2 — `ABDM_CLIENT_ID`/`ABDM_CLIENT_SECRET`). **Scrape the search backend to district.** Coverage growing/incomplete. **Cost:** Free.

**I6 — NHPR / HPR** 🟢 (doctors/nurses/pharmacists by category; address→district) — `https://nhpr.abdm.gov.in/`, public search `https://nhpr.abdm.gov.in/nhpr/v4/hpr/publicSearch`. **Cost:** Free.

**I7 — PMJAY Empanelled Hospitals (HEM)** 🟢 (**district**-filterable; private + public hospitals + **specialties** → chronic signal)
- Search: `https://hospitals.pmjay.gov.in/Search/` (State → District → Speciality → Public/Private). PDF list `https://nha.gov.in/img/resources/PMJAY-Hospital-List.pdf`. **Scrape backing AJAX**; returns name/address/specialities/type/NABH grade. ~36k+ hospitals. **Cost:** Free.

**I8 — AB-HWC / Ayushman Arogya Mandir** 🟢 (district count of primary-care centres + NCD-screening reach → chronic) — `https://ab-hwc.nhp.gov.in/` (redirects to `aam.mohfw.gov.in`); map/table `https://nhsrcindia.org/AB-HWCs-map-table`. **Cost:** Free.

**I9 — IMR / NMR (NMC)** 🟢 (allopathic doctors; **state**, district only via address parsing — weak; no bulk API) — `https://www.nmc.org.in/information-desk/indian-medical-register/`. Use state doctor ratios apportioned to districts. **Cost:** Free.

**I10 — PCI + CDSCO** 🟢 (registered pharmacists **state**; district retail-chemist counts **not** centrally published → use HFR + OSM proxy) — PCI `https://pci.gov.in/en/pharmacy-council-of-india/pharmacist-dashboard/`; CDSCO `https://cdsco.gov.in/`. **Cost:** Free.

**I11 — AYUSH (NAM)** 🟢 — data.gov.in verified: **AYUSH Registered Practitioners** (state-level, e.g. 2023 id `27aae2fb-3a08-4339-a963-7b79c7ce567f`) and **District Wise Ayush Hospitals** (district, id `7be9a8fa-b889-4c03-9dc7-b07e681d501a`); discover more via `filters[title]=Ayush`. NAM portal `https://namayush.gov.in/`. `DATA_GOV_IN_API_KEY`. **Cost:** Free.

**I12 — OpenStreetMap Overpass** 🟡 (**best free district pharmacy/clinic-density proxy**)
- Overpass API: `https://overpass-api.de/api/interpreter` (mirror `https://overpass.kumi.systems/api/interpreter`). Query `amenity=pharmacy|clinic|hospital|doctors`, `healthcare=*` clipped to district area → `out count;`. Point → aggregate to any district polygon. **License:** ODbL (attribution + share-alike). Coverage uneven (urban bias) — relative proxy. **Cost:** Free.

**I13 — Google Places API** 🔴 **PAID/quota** — `GOOGLE_MAPS_API_KEY` with billing; ToS forbids bulk caching. **Prefer OSM (I12).** *(The `Google_Sheet_Api.json` key could be extended to Maps, but keep this optional/paid.)*

---

### 4.4 Healthcare Spending, Affordability, Insurance & Pharma Market

| # | Source | Auth | Granularity | Access | Key |
|---|---|---|---|---|---|
| S1 | National Health Accounts (NHA) | 🟢 NHSRC/MoHFW | National + State | PDF report | none |
| S2 | HCES 2022-23 (Consumption/MPCE + medical) | 🟢 NSSO/MoSPI | State (microdata has dist. codes) | Factsheet PDF + microdata | free login |
| S3 | NSS 75th Round — Health (2017-18) | 🟢 NSO/MoSPI | State + microdata | Report PDF + microdata | free login |
| S4 | **PMJAY Insights Dashboard** | 🟢 NHA | **District** ✓ | Web dashboards (scrape) | none |
| S5 | **NFHS-5 (insurance coverage)** | 🟢 IIPS/MoHFW | **District (707)** ✓ | PDF fact sheets + microdata | none |
| S6 | **Jan Aushadhi / PMBJP Kendras** | 🟢 PMBI/DoP | **District** (count) ✓ | Locate-Kendra portal (scrape) + PDF | none |
| S7 | NPPA ceiling prices / NLEM | 🟢 NPPA/DoP | National (product) | PDF/XLSX | none |
| S8 | CDSCO drug approvals / licenses (SUGAM) | 🟢 CDSCO | National + State | Web tables | none |
| S9 | IRDAI Insurance Statistics Handbook | 🟢 IRDAI | National + partial State | PDF/XLSX | none |
| S10 | data.gov.in (Ayushman/health datasets) | 🟢 NIC | Mixed (some district) | REST API + bulk | `DATA_GOV_IN_API_KEY` |
| S11 | State scheme dashboards (MJPJAY, CMCHIS…) | 🟢 State govts | **District** ✓ | Dashboards (scrape) | varies |
| S12 | SECC 2011 (income/deprivation proxy) | 🟢 MoRD | **District** ✓ | Portal download | none |

**S1 — National Health Accounts (NHA)** 🟢 (definitive OOP/health-spend; national + **state** GHE — apportion to districts) — NHA 2021-22 PDF `https://nhsrcindia.org/sites/default/files/2024-09/NHA%202021-22.pdf`; 2022-23 release `https://www.pib.gov.in/PressReleaseIframePage.aspx?PRID=2058791`. OOPE % (43.4%), per-capita spend (₹2,767), state GHE, insurance share. **Cost:** Free.

**S2 — HCES 2022-23** 🟢 (household **medical MPCE**; state-representative, microdata has district/NSS-region codes — approximate at district) — factsheet `https://www.mospi.gov.in`; microdata `https://microdata.gov.in/NADA/index.php/catalog/224`; community dump `https://github.com/advaitmoharir/hces_2022`. Medical (hospitalisation→acute) & (non-hospitalisation→chronic/OTC) spend; MPCE fractiles = income proxy. **Cost:** Free.

**S3 — NSS 75th Round Health (2017-18)** 🟢 (medical expenditure per hospitalisation, insurance %, catastrophic spend; state + microdata) — microdata `https://microdata.gov.in/NADA/index.php/catalog/152`; summary `https://mospi.gov.in/sites/default/files/announcements/Summary%20Analysis_Report_586_Health.pdf`. **Cost:** Free.

**S4 — PMJAY Insights Dashboard** 🟢 **⭐ district-granular** (best free insurance-penetration + utilization district proxy)
- Hub: `https://insights.pmjay.gov.in/` → **State & District Performance Dashboard**, Procedure-Hospital, Village Penetration. Empanelled search `https://hospitals.pmjay.gov.in/Search/`.
- **Scrape** the Tableau/JSON backing calls: Ayushman cards created (coverage), empanelled hospitals (supply), authorized admissions & value (demand/claims); procedure mix → chronic vs acute case-split. Near-real-time. **Cost:** Free.

**S5 — NFHS-5 (insurance coverage)** 🟢 **⭐ district (707)** — "% households with any member covered by health insurance/financing scheme" per district (compendium `https://dhsprogram.com/pubs/pdf/OF43/NFHS-5_India_and_State_Factsheet_Compendium_Phase-II.pdf`). *(Same source as H1.)* **Cost:** Free.

**S6 — Jan Aushadhi / PMBJP** 🟢 **⭐ district** (best free **generic-market** proxy: kendra density; **sales only national** → impute district sales = kendra count × avg sales/kendra)
- Locate Kendra (state→district filter, scrapeable AJAX/JSON): `https://janaushadhi.gov.in/locate-kendra`; about `https://janaushadhi.gov.in/about-pmbjb`; district PDFs on the site. ~19,500 kendras; avg ~₹1.5 lakh/kendra/month. **Cost:** Free.

**S7 — NPPA ceiling prices / NLEM** 🟢 (national product-level price benchmarks; drug-price normalization) — `https://nppa.gov.in/en`, compendium `https://nppa.gov.in/compendiumofprice`. ~900+ scheduled formulations, generic vs branded gap. **Cost:** Free.

**S8 — CDSCO / SUGAM** 🟢 (supply-side maturity proxy; approvals national, manufacturing/sale licenses state → geocode addresses) — approved drugs `https://cdsco.gov.in/opencms/opencms/en/Approval_new/Approved-New-Drugs/`; SUGAM `https://cdscoonline.gov.in/CDSCO/homepage`. **Cost:** Free.

**S9 — IRDAI Handbook** 🟢 (private-insurance penetration/density; national + partial state normalizer — complements PMJAY public coverage) — `https://irdai.gov.in/handbook-of-indian-insurance`. **Cost:** Free.

**S10 — data.gov.in (Ayushman/health)** 🟢 ⚠️ **CORRECTION:** the Ayushman/AB-PMJAY datasets on data.gov.in (cards created, Arogya Mandir counts) are **State/UT-level only** — there is no reliable district AB-HWC resource here. For **district** Ayushman coverage use the **PMJAY Insights dashboard (S4)** or **NFHS-5 insurance field (S5/H2)**. Discover via `filters[title]=Ayushman` (§5A). `DATA_GOV_IN_API_KEY`. **Cost:** Free.

**S11 — State scheme dashboards** 🟢 (fills district insurance-utilization where states run big parallel schemes) — e.g. UP `https://data.ayushmanup.in/_dashboard/dashboard-pmjay-district`, Maharashtra MJPJAY `https://www.jeevandayee.gov.in/`, TN CMCHIS, Rajasthan Chiranjeevi, Telangana Aarogyasri. Scrapeable district tables (coverage uneven). **Cost:** Free.

**S12 — SECC 2011** 🟢 (district income/affordability proxy — deprivation categories, asset ownership; pair with NFHS wealth for freshness) — `https://secc.gov.in/`. **Cost:** Free.

---

### 4.5 GIS / District Boundaries (for maps & heatmaps)

| # | Source | Auth | Units | Access | Key | License |
|---|---|---|---|---|---|---|
| G1 | **DataMeet Maps** ⭐ | 🟡 community | District (2011 codes) | GitHub download | none | CC BY 4.0 (**commercial-safe**) |
| G2 | **geoBoundaries** ⭐ | 🔵 W&M geoLab | District ADM2 (736, 2021) | REST API + GitHub | none | ODbL/CC BY |
| G3 | GADM 4.1 | 🔵 UC Davis | District ADM2 (676) | Direct download | none | **non-commercial only** ⚠️ |
| G4 | Survey of India | 🟢 SoI/DST | District | Web portal (login) | login | Govt |

**G1 — DataMeet Maps** 🟡 **recommended** (aligned to 2011 Census district codes → matches Census/NFHS keys; commercial-friendly)
- `https://github.com/datameet/maps` → `Districts/Census_2011/2011_Dist.shp` (+ .dbf/.prj/.shx, WGS84). Browser `https://projects.datameet.org/maps/districts/`.

**G2 — geoBoundaries** 🔵 **recommended for automation** (API returns direct download URLs; 736 ADM2, LGD-sourced, more current)
- API (live): `https://www.geoboundaries.org/api/current/gbOpen/IND/ADM2/` → GeoJSON `https://github.com/wmgeolab/geoBoundaries/raw/9469f09/releaseData/gbOpen/IND/ADM2/geoBoundaries-IND-ADM2.geojson`. Also on HDX `https://data.humdata.org/dataset/geoboundaries-admin-boundaries-for-india`.

**G3 — GADM 4.1** 🔵 (676 districts; **free for academic/non-commercial only** — avoid for a commercial pharma deliverable) — `https://gadm.org/download_country.html`.

**G4 — Survey of India** 🟢 (authoritative national mapping agency; bulk district shapefiles behind login — DataMeet is the practical open substitute) — `https://onlinemaps.surveyofindia.gov.in`.

---

### 4.6 Paid commercial pharma-sales (reference only — NOT used)

These are the only sources giving **actual district/territory pharma SALES** — all **PAID/subscription**. Documented so you can justify the free proxies. **Do not budget for these; the case rewards public-domain proxy logic.**

| Source | Auth | Granularity | Why it matters | Free substitute |
|---|---|---|---|---|
| **IQVIA (PharmaTrac / IPM)** 🔴 | commercial | State / metro / territory | Ground-truth market size, therapy splits, growth | Jan Aushadhi imputed sales + PMJAY claims + HCES medical MPCE + NPPA prices |
| **AIOCD-AWACS (SSA)** 🔴 | commercial | Stockist / territory (sub-district) | Most granular secondary sales | Same + CDSCO/State-FDA chemist-license density |
| **SMSRC / RK SWAMY** 🔴 | commercial | Prescription/retail panel | Prescription behaviour, specialty mix | NFHS district NCD prevalence + PMJAY procedure-mix |

- IQVIA: `https://www.iqvia.com/insights/the-iqvia-institute/available-iqvia-data` · AIOCD-AWACS: `https://www.aiocdawacs.com/ProductDetail.aspx`

> **Free sales-approximation formula:**
> `District pharma proxy ≈ f(district population × state per-capita medical MPCE [HCES] × district affordability index [SECC/NFHS wealth]) + Jan-Aushadhi imputed generic sales + PMJAY claim value`.
> Validate the *ranking* (not absolute ₹) against any one-off IQVIA/AWACS state figures if available.

---

## 5. Access recipes (scrape / API / download)

**A. data.gov.in REST API (the main API path) — VERIFIED 2026-07-14 with the project key.**
> ⚠️ **Do not use `/catalog/<slug>` URLs** — data.gov.in restructured and most old slugs 404. Address data by **resource-id**. **Discovery search works via `filters[title]=`, NOT `query=`** (the `query` param is ignored and returns a default list).

```python
import os, requests
KEY = os.environ["DATA_GOV_IN_API_KEY"]

# 1) DISCOVER resource-ids by title substring (server-side filter that actually works):
disc = requests.get("https://api.data.gov.in/lists", timeout=45, params={
    "api-key": KEY, "format": "json", "limit": 10,
    "filters[title]": "National Family Health Survey"}).json()
for r in disc["records"]: print(r["index_name"], "|", r["title"])

# 2) PULL a resource's rows by id (paginate with offset/limit; max ~ a few k/call):
rid = "cf80173e-fece-439d-a0b1-6e9cb510593d"           # NFHS-5 district factsheets
rows = requests.get(f"https://api.data.gov.in/resource/{rid}", timeout=60, params={
    "api-key": KEY, "format": "json", "limit": 1000}).json()["records"]
# helper alt: pip install datagovindia (downloads full metadata catalog, searches locally)
```

**Verified working district-level resource-ids (tested, return data):**
| Dataset | resource-id | Rows | District? |
|---|---|---|---|
| **NFHS-5 India Districts Factsheets** (109 indicators incl. blood-sugar, BP, BMI, cancer, tobacco, immunization, anaemia, insurance, OOP) | `cf80173e-fece-439d-a0b1-6e9cb510593d` | 707 | ✅ yes |
| **district wise health centres** (SC/PHC/CHC/SDH/DH — one tab-packed column, split on `\t`) | `6t201darmc8ocx5p06s9db1ycd86afce` | 707 | ✅ yes |
| **Primary Census Abstract 2011 – India** (district/sub-district; India totals) | `0764657f-00ec-4c6b-9ece-2d7b8a7401fa` | 108 | ✅ (per-state files for full district rows) |
| PCA 2011 per-state (e.g. Rajasthan / Gujarat / Kerala) | `11268466-…` / `4c0b7dd3-…` / `4bdd67c0-…` | many | ✅ yes |
| District Wise Ayush Hospitals | `7be9a8fa-b889-4c03-9dc7-b07e681d501a` | — | ✅ yes |

**On data.gov.in but only STATE-level (use the primary portal for district granularity):** Ayushman/AB-PMJAY cards & Arogya Mandir, Item-wise HMIS reports (per state/year aggregate), AYUSH registered practitioners, most RHS PHC/CHC count tables.

**Ready-to-use URLs (append `&format=csv` for a one-click CSV download):**
| Dataset | Web page | API endpoint (stable — use this) |
|---|---|---|
| NFHS-5 district factsheets (707×109) | ❌ removed (redirects to `/not-found`) — API only; browsable mirror on AIKosh | `https://api.data.gov.in/resource/cf80173e-fece-439d-a0b1-6e9cb510593d?api-key=<KEY>&format=json&limit=1000` |
| district wise health centres (707) | `visualize.data.gov.in` (no clean page) | `https://api.data.gov.in/resource/6t201darmc8ocx5p06s9db1ycd86afce?api-key=<KEY>&format=json&limit=1000` |
| PCA 2011 – India | ✅ `https://www.data.gov.in/resource/primary-census-abstract-2011-india` | `https://api.data.gov.in/resource/0764657f-00ec-4c6b-9ece-2d7b8a7401fa?api-key=<KEY>&format=json` |
| PCA 2011 – per state (e.g. Rajasthan) | ✅ `https://www.data.gov.in/resource/primary-census-abstract-2011-rajasthan` | `https://api.data.gov.in/resource/11268466-4ee5-465e-af48-ff4ac86aac24?api-key=<KEY>&format=json&limit=1000` |
| District Wise Ayush Hospitals | `karnataka.data.gov.in` | `https://api.data.gov.in/resource/7be9a8fa-b889-4c03-9dc7-b07e681d501a?api-key=<KEY>&format=json` |

> **Rule:** data.gov.in **web pages are unstable** (removed/redirected without notice); always fetch by **`api.data.gov.in/resource/<id>`** — those endpoints stay live even when the HTML page 404s.

**B. PDF table extraction (RHS, NITI MPI, NCRP, IDSP, TB Report):**
```python
import camelot           # or tabula-py (needs Java)
tables = camelot.read_pdf("RHS_2022-23.pdf", pages="all", flavor="lattice")
df = tables[0].df
```

**C. Portal/dashboard scraping (PMJAY, Jan Aushadhi, HFR, HMIS) — hit the backing JSON, not the rendered HTML:**
```python
# 1. Open the portal in browser DevTools → Network tab → find the XHR/AJAX call the district filter fires.
# 2. Replay it with requests/httpx, iterating state→district codes.
# Jan Aushadhi "locate-kendra" and PMJAY "hospitals.pmjay.gov.in/Search" both expose such POST endpoints.
```

**D. OSM Overpass (pharmacy/clinic density per district):**
```
[out:json][timeout:120];
area["ISO3166-2"="IN-MH"]->.state;                 // or use a district admin_level=5/6 relation
( node["amenity"="pharmacy"](area.state);
  node["amenity"="clinic"](area.state); );
out count;
```

**E. GIS boundaries (geoBoundaries API → GeoJSON):**
```python
import requests
meta = requests.get("https://www.geoboundaries.org/api/current/gbOpen/IND/ADM2/").json()
geojson_url = meta["gjDownloadURL"]
```

> **Reachability caveat:** many `.gov.in` portals (data.gov.in, NPPA, PMJAY, NMC, rchiips) return 403/SSL errors to headless fetchers (bot protection) but load fine in a real browser/`requests` with a normal User-Agent. Set a browser User-Agent, tolerate their cert chain, and rate-limit scraping.

---

## 6. Database Design

**Goal: a live, working web app to demo during the presentation.** The single platform is therefore **Firebase** (project `medicine-attractive-index`) — one system that covers all three needs: **Cloud Firestore** = the database, **Firebase Storage** = map/GeoJSON assets, **Firebase Hosting** = the public live-app URL you open on stage. The heavy index build runs offline in Python and *publishes* results into Firestore; the app just reads them. The GCP service account (`sodium-primer-502411-i9`) + Sheets API + linked Sheet are kept as an **optional** collaborative curation grid during data prep — not required for the app, and skippable if you want to stay on one platform.

### 6.1 Architecture — ONE platform: Firebase (offline build → live app)

**Decision:** split the system into an **offline build** (runs once on your laptop, does the heavy data work) and an **online serve** (the live Firebase app you demo). Only one *platform* is used at runtime — **Firebase** — which covers database (Firestore), file storage (Storage), and web hosting (Hosting) with a single set of credentials (`Firebase_Service_Account.json`).

```
 ══ OFFLINE BUILD (Python, your laptop — run before the presentation) ══
 ┌────────────────────────────────────────────────────────────────────┐
 │ 1. Ingest  API / download / scrape / PDF-parse  → data/raw/         │
 │ 2. Clean & key-standardize (LGD crosswalk)      → data/interim/     │
 │ 3. Model    normalize → weight → 3 indices       → mai_output.csv   │
 │ 4. Publish  Firebase Admin SDK writes results ───────────┐          │
 └──────────────────────────────────────────────────────────┼─────────┘
                                                             ▼
 ══ ONLINE SERVE (Firebase — running live during the demo) ══
 ┌────────────────────────────────────────────────────────────────────┐
 │  Cloud Firestore  ── districts, mai_scores, indicator_catalog …     │
 │  Firebase Storage ── india_adm2.geojson (choropleth boundaries)     │
 │  Firebase Hosting ── the SPA (React/Vue/vanilla + Leaflet/MapLibre) │
 │        reads Firestore live  →  rankings · maps · therapy toggle    │
 └────────────────────────────────────────────────────────────────────┘
                         ▲  open this URL on stage
```

**Why Firebase is the right single platform for a live demo:**
- **One platform, three jobs** — Firestore (DB) + Storage (GeoJSON/assets) + Hosting (the app URL) under the project you already have (`medicine-attractive-index`). No server to run on stage; just open a URL.
- **Fast, real-time reads** — 700 district docs + score docs load instantly; the client SDK streams updates, so a live re-rank looks impressive.
- **Free tier is plenty** — Spark plan easily covers ~700 docs and a demo's read volume; Hosting gives an HTTPS URL + CDN out of the box.
- **Deterministic publish** — the offline build upserts by `lgd_district_code`, so re-running the model just refreshes the same docs the app is already reading.

> The **modeling still happens in Python/pandas offline** (Firestore is a serving DB, not an analytics engine). If you want a collaborative curation grid while preparing data, use the optional Google Sheet (§6.7) — but the app itself needs only Firebase.

### 6.2 District master key strategy (the critical join problem)

Sources use **different district vintages**: Census 2011 (640, census codes), NFHS-5 (707, 2017 boundaries), RHS/current (770+, LGD codes), GBD (state). You **must** standardize on one canonical key or joins silently break.

**Canonical spine = LGD (Local Government Directory) district code** from `https://lgdirectory.gov.in/` (the government's authoritative, current district registry), with a **crosswalk** mapping every source's key to it:

```
dim_district_crosswalk:
  lgd_district_code   (PK, canonical)
  lgd_district_name
  state_lgd_code, state_name, region            # N/S/E/W/NE/Central
  census2011_code                               # → Census, SECC, DataMeet shapefile
  nfhs5_district_name  (+ fuzzy-match confidence)# → NFHS-5/4
  geoboundaries_shapeID                          # → maps
  parent_district_lgd_code                       # for post-2011 district splits
  notes                                          # merges/splits/renames
```
- Build it once (semi-manually + fuzzy matching on names within state); keep it as `data/interim/dim_district.csv` in the build repo and publish it to the Firestore **`districts/{lgd_district_code}`** collection — this canonical code is the doc ID everything else references.
- Handle **new districts carved out after 2011**: inherit 2011-based values from the parent district (flag `is_imputed_from_parent=true`) until fresher data exists.

### 6.3 The database = Cloud Firestore (collections the app reads)

Written by the offline build via `Firebase_Service_Account.json`; read live by the app. Doc IDs = canonical `lgd_district_code` for deterministic upserts. `indicator_catalog` + `sources` + `mai_runs` carry the **variable dictionary, data lineage, assumptions and reproducibility** the rubric rewards.

```
districts/{lgdDistrictCode}                        # master profile — 1 doc/district
  ├─ lgd_district_code (= doc id), name, state, state_lgd_code, region
  ├─ census2011_code, nfhs5_name, geoboundaries_shapeID
  ├─ population_2011, population_latest_est, area_sq_km, urban_pct
  ├─ centroid: <geopoint>, data_completeness: 0.0–1.0, is_imputed_from_parent
  ├─ updated_at
  └─ indicators/{indicatorCode}                    # subcollection — 1 doc/indicator
        └─ value, unit, year, source_id, is_imputed, method

mai_scores/{lgdDistrictCode}                        # FINAL OUTPUT the app ranks & maps
  ├─ name, state, region
  ├─ overall_score, overall_rank, overall_tier      # tier = A/B/C/D or quintile
  ├─ chronic_score, chronic_rank, chronic_tier
  ├─ acute_score,   acute_rank,   acute_tier
  ├─ pillar_scores: { macro, chronic_burden, acute_burden, provider, access, spend, leading }
  ├─ current_vs_future: { current_score, projected_score, growth_flag }
  └─ model_version

indicator_catalog/{indicatorCode}                   # VARIABLE DICTIONARY
  ├─ code, name, description, unit
  ├─ pillar (macro|chronic_disease|acute_disease|provider|access|spend|leading)
  ├─ therapy_relevance: [overall, chronic, acute],  direction (+/-)
  ├─ source_id, transform, default_weight, rationale

sources/{sourceId}                                  # SOURCE REGISTRY / lineage (mirrors §4)
  ├─ name, agency, authenticity (gov|academic|community|paid)
  ├─ url, access_method (api|download|scrape|pdf), api_key_env
  ├─ granularity, latest_year, format, license, cost

mai_runs/{runId}                                    # REPRODUCIBILITY — 1 doc/model run
  ├─ model_version, method (weighted-zscore|PCA|entropy|AHP|ML)
  ├─ weights, normalization, missing_data_strategy, validation_metrics, created_at, author
```

**Publish pattern (offline, Firebase Admin SDK):**
```python
import os, firebase_admin
from firebase_admin import credentials, firestore
firebase_admin.initialize_app(credentials.Certificate(os.environ["FIREBASE_CREDENTIALS"]))
db = firestore.client()

batch = db.batch()
for row in mai_output.itertuples():                 # ~700 rows
    ref = db.collection("mai_scores").document(row.lgd_district_code)
    batch.set(ref, row._asdict())                   # upsert by district code
    if row.Index % 400 == 0: batch.commit(); batch = db.batch()
batch.commit()
```

**Firestore security rules for the demo (public read-only, no writes from the client):**
```
match /{col}/{doc} { allow read: if col in ['districts','mai_scores','indicator_catalog','sources','mai_runs'];
                     allow write: if false; }   // only the Admin SDK (offline build) writes
```

### 6.4 Build files (offline) & map assets (Firebase Storage)

Raw source files are files, not DB rows — keep them local during the build; push only the app's map layer to Firebase Storage.

```
data/                                            # local build workspace (git-ignore big binaries)
  raw/{source_id}/{ingest_YYYYMMDD}/<file>        # immutable, exactly as fetched
  interim/{source_id}/<parsed>.csv                # cleaned tables + dim_district.csv
  exports/mai_output.csv, exports/maps/*.png      # for the PPT

Firebase Storage (gs://medicine-attractive-index.firebasestorage.app):
  geo/india_adm2.geojson                          # district boundaries for the choropleth
```
> For a demo you can also just **bundle `india_adm2.geojson` in the Hosting `public/` folder** (one fetch, no Storage CORS setup) — simplest path. Use Storage only if you want to swap boundaries without redeploying.

### 6.5 End-to-end pipeline (build → publish → deploy)

1. **Ingest** — per source: API pull / bulk download / scrape backing-JSON / PDF-parse → `data/raw/`.
2. **Parse & clean** — normalize columns, units, years → `data/interim/*.csv`.
3. **Key-standardize** — join each table to the `dim_district` crosswalk (§6.2) → attach canonical `lgd_district_code`; log unmatched rows.
4. **Stack & impute** — assemble a long fact table; apply §7 proxy/imputation for missing districts/years; flag `is_imputed=true`, record each decision.
5. **Pivot** — build the wide feature matrix (~700 rows × N indicators).
6. **Model** — normalize (z-score/min-max, winsorize), weight (equal / entropy / PCA / AHP / ML), compute **Overall / Chronic / Acute** scores + ranks + tiers + current-vs-future view.
7. **Publish** — Admin SDK upserts `districts`, `mai_scores`, `indicator_catalog`, `sources`, `mai_runs` into Firestore; upload `india_adm2.geojson` to Storage (or `public/`).
8. **Deploy** — `firebase deploy` pushes the app to Hosting → you get the HTTPS demo URL.

### 6.6 The live demo app (Firebase Hosting)

A single-page app served from Firebase Hosting that reads Firestore live — this is what you open during the presentation.

**Stack (all free, self-contained):**
- **Firebase Hosting** — HTTPS URL + CDN (`firebase init hosting` → `public/`).
- **Firestore Web SDK** (client, read-only per the rules above) — no backend server.
- **Map:** **Leaflet + OSM tiles** or **MapLibre GL JS** (both open-source, no paid token) rendering the district **choropleth/heatmap** from `india_adm2.geojson`, colored by the selected score.
- **UI:** React/Vue or vanilla JS + a chart lib (Recharts/Chart.js) for rankings and therapy comparisons.

**Demo features (map to the rubric's "Visualization & Insights"):**
- **Index toggle** — switch the whole view between **Overall / Chronic / Acute** (rubric: three indices, therapy-wise comparison).
- **District choropleth/heatmap** — color-graded map; hover/click a district for its profile.
- **Ranked table + search** — top/bottom districts, filter by state/region.
- **District drill-down** — pillar breakdown (macro, disease burden, access, spend…) + the indicators behind the score, pulled from `districts/{code}/indicators` (rubric: explainability).
- **Current vs Future toggle** — show `current_score` vs `projected_score` and flag high-growth districts (rubric: forward-looking view, "future high-growth districts").
- **Sales-force lens** — highlight priority districts for deployment/territory planning (rubric: business actionability).

**Deploy:**
```bash
firebase login
firebase use medicine-attractive-index
firebase deploy --only hosting,firestore:rules
# → live URL e.g. https://medicine-attractive-index.web.app
```

### 6.7 (Optional) Google Sheets — collaborative curation only

If teammates want to eyeball/edit indicators during data prep, mirror the long fact table + variable dictionary into the linked Sheet (`GSHEET_ID`) via the GCP service account. Purely a convenience during the build; the app does not depend on it, so it can be skipped entirely to stay on one platform (Firebase).

---

## 7. Data gaps & proxy strategy

| Gap | Reality | Proxy / mitigation |
|---|---|---|
| **District pharma sales** | Only paid (IQVIA/AWACS) | Jan Aushadhi imputed sales + PMJAY claim value + HCES medical MPCE × population × affordability (§4.6 formula) |
| **District income / GDP** | DDP only ~26 states; RBI state-only | SHRUG consumption + night-lights; NFHS wealth index; SECC deprivation; apportion state NSDP |
| **Census vintage** | 2011 (2021 census delayed) | Use NFHS-5 (2019-21) & NITI MPI (2023) as fresher district layers; flag vintage |
| **District population projection** | Official = state only | 2011 base × state growth; WorldPop grid; SHRUG night-lights growth |
| **Chronic anchors (GBD, INDIAB)** | State-level | Downscale to districts using NFHS district BP/glucose/BMI signals; mark `is_imputed` |
| **Cancer (NCRP)** | 36 registries only | Anchor registry districts; interpolate others from risk factors + GBD |
| **Doctors/pharmacists** | NMR/NHP state-level | State ratios × district population; refine with HFR/NHPR district records + OSM density |
| **Insurance (IRDAI)** | National/state | District via NFHS-5 coverage + PMJAY cards created |
| **New post-2011 districts** | Missing in 2011 sources | Inherit parent-district values; flag `is_imputed_from_parent` |

**Golden rule:** every imputed/proxy value carries `is_imputed=true`, a `method`, and an `assumptions_log` entry — the rubric explicitly scores "use of proxy logic," "clarity of assumptions," and "handling of missing data."

---

## 8. Recommended build sequence

1. **Provision** — create `DATA_GOV_IN_API_KEY`; set env vars (§3.2); in the Firebase console for project `medicine-attractive-index`, enable **Firestore**, **Storage**, and **Hosting**; confirm the Storage bucket name.
2. **Build the district spine** — assemble `dim_district` crosswalk (LGD ⇄ Census2011 ⇄ NFHS-5 ⇄ geoBoundaries) for all 700+ districts.
3. **Land the district-complete layers first** (highest ROI, true 700+ coverage): **NFHS-5** (H1), **HMIS** (H3), **RHS 2022-23** (I1/I2), **PMJAY** (S4/I7), **Jan Aushadhi** (S6), **NITI MPI** (D3), **Census PCA** (D1), **NFHS insurance** (S5).
4. **Add acute infectious layer** — **EpiClim** (H6) + IDSP (H5) + NCVBDC (H8) + Ni-kshay (H9).
5. **Add anchors to downscale** — GBD (H4), ICMR-INDIAB (H10), NCRP (H7), NHA (S1), HCES (S2).
6. **Density proxies** — HFR (I5) + OSM Overpass (I12) for pharmacy/clinic density.
7. **Boundaries** — geoBoundaries (G2) / DataMeet (G1) → `india_adm2.geojson` for the choropleth.
8. **Model** — normalize → weight → three indices + ranks + tiers + current-vs-future.
9. **Publish & deploy** — Admin SDK upserts scores into **Firestore**; upload GeoJSON; `firebase deploy` the Hosting app → open the live URL in the presentation.

---

### Appendix — one-line source index (quick copy)

```
D1 Census2011  https://censusindia.gov.in/census.website/en/data
D2 data.gov.in https://www.data.gov.in            (API key)
D3 NITI MPI    https://www.niti.gov.in/node/359
D5 DDP/MoSPI   https://mospi.gov.in/137-regional-accounts
D7 SHRUG       https://www.devdatalab.org/shrug
H1 NFHS-5      http://rchiips.org/nfhs/Factsheet_Compendium_NFHS-5.shtml
H3 HMIS        https://hmis.mohfw.gov.in/
H4 GBD         https://vizhub.healthdata.org/gbd-results/
H6 EpiClim     https://arxiv.org/html/2501.18602v1
H7 NCRP        https://ncdirindia.org/All_Reports/PBCR_Annexures/Default.aspx
H8 NCVBDC      https://ncvbdc.mohfw.gov.in/
H9 Ni-kshay    https://reports.nikshay.in/reports/tbnotification
H10 INDIAB     https://www.thelancet.com/journals/landia/article/PIIS2213-8587(23)00119-5/fulltext
I1 RHS         https://www.mohfw.gov.in/?q=reports-23
I5 HFR         https://facility.abdm.gov.in/searchV2
I7 PMJAY-HEM   https://hospitals.pmjay.gov.in/Search/
I8 AB-HWC      https://ab-hwc.nhp.gov.in/
I12 OSM        https://overpass-api.de/api/interpreter
S1 NHA         https://nhsrcindia.org/
S2 HCES        https://microdata.gov.in/NADA/index.php/catalog/224
S4 PMJAY-ins   https://insights.pmjay.gov.in/
S6 JanAushadhi https://janaushadhi.gov.in/locate-kendra
S7 NPPA        https://nppa.gov.in/compendiumofprice
S9 IRDAI       https://irdai.gov.in/handbook-of-indian-insurance
S12 SECC       https://secc.gov.in/
G1 DataMeet    https://github.com/datameet/maps
G2 geoBound.   https://www.geoboundaries.org/api/current/gbOpen/IND/ADM2/
LGD spine      https://lgdirectory.gov.in/
```
