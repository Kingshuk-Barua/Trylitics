# SCRAPING CHECKLIST — Trilytics District-Level MAI

> **This file is a RESUMABLE work-log.** It is written for a Claude account that has **zero prior context** and is driving a browser via the **Claude Chrome extension**. If your session/token expires mid-way, a fresh Claude can reopen this file, read the **STATE** table, and continue from the first unchecked `[ ]` box. **After completing any step, tick its box and fill the "saved to / rows / date" cell.**

---

## 0. What this project is (30-second brief)
Building a **District-Level Market Attractiveness Index** for the Indian pharma market across ~700 districts (Sun Pharma "Trilytics" case, done as a **student academic project**). We need free, district-level India data. This checklist covers **acquiring the raw data**. Full source catalog + DB design live in [DATA_SOURCES_AND_DB_DESIGN.md](DATA_SOURCES_AND_DB_DESIGN.md); all credentials/resource-IDs in [Credentials/DATA_GOV_IN_API_KEY.json](../Credentials/DATA_GOV_IN_API_KEY.json).

## Ground rules for whoever executes this
1. **Only a personal email is available — no organizational URL/email.** So **SKIP every source that requires org registration** (see §1). Do not try to register on them.
2. **Verify before trusting.** This project was previously burned by dead URLs. For every fetch, confirm you got real rows (not an error/empty/`/not-found`). If a call fails, **write the exact error into the STATE table** — do not silently skip.
3. **Save raw output verbatim** into `data/raw/<source>/` (create the folders). Never hand-edit raw files.
4. **Use the Chrome extension** to do the fetching (open the API URL → the browser shows JSON → save it; or run a `fetch()` in DevTools console and download). A Python fallback is given in §4 if you prefer.
5. Tick boxes and update the **STATE** table as you go.

---

## 1. ⛔ SKIP — do NOT attempt (org-gated or dead)
| Source | Why skip |
|---|---|
| MoSPI eSankhyiki (Economic Census) | Registration needs an `organization`; also low value (data is 1998/2005/2013). |
| NDAP (NITI Aayog) | Needs sign-in + governance risk (non-`.gov.in` vendor host). |
| ABDM sandbox (HFR/NHPR) | Org onboarding; won't yield a bulk district dump anyway. |
| IDSP / NCVBDC / IHIP (MoHFW) | HTTP 000 — genuinely unreachable, even from an Indian IP. |
| rchiips.org (NFHS canonical) | Broken TLS + 404. Dead. |
| data.gov.in `district_wise_health_centres` | `active:0`, deactivated, flaky. |
| data.gov.in `District Wise Ayush Hospitals` | Only 2 rows, and it's Karnataka *college* seats — not hospitals. |

---

## 2. ✅ READY — scrape these (no registration, or personal email only)

Legend: **REG** = registration needed. 🟢 none · 🟡 personal email OK · Priority: ⭐ = core.

| # | Source | REG | District? | Access | Priority |
|---|---|---|---|---|---|
| A | **India Data Portal — NFHS-4 & NFHS-5** | 🟢 none | ✅ 698 dist + `district_code` | CKAN JSON API | ⭐⭐⭐ |
| B | **India Data Portal — Census PCA (Districts)** | 🟢 none | ✅ | CKAN JSON API | ⭐⭐ |
| C | **India Data Portal — SECC 2011** | 🟢 none | ✅ | CKAN JSON API | ⭐⭐ |
| D | **data.gov.in — NFHS-5 factsheet (707×109)** | ✅ have key | ✅ 707 (names) | REST API | ⭐⭐ |
| E | **geoBoundaries — district polygons** | 🟢 none | ✅ 735 | GeoJSON download | ⭐⭐ (maps) |
| F | **India Data Portal — HMIS (sub-district)** | 🟢 none | ✅ 547k rows | CKAN JSON API | ⭐ (stale→2021) |
| G | **Ni-kshay — district TB (public/private)** | 🟢 none* | ✅ | POST + session cookie | ⭐ |
| H | **PMJAY — empanelled hospitals** | 🟢 none* | ✅ | POST + session | ⭐ |
| I | **SHRUG (Dev Data Lab)** | 🟡 email opt. | ✅ | zip download (academic-OK) | optional |
| J | **DHS API (state-level only)** | 🟢 none | ❌ state | REST API | optional anchor |

\* no account, but you must load the page first to get a session cookie.

---

## 3. ▶ EXECUTION STEPS (do in this order; tick as you finish)

> Base for A/B/C/F: `https://ckan.indiadataportal.com/api/3/action/datastore_search`
> All CKAN calls are **GET** and return JSON in the browser. Paginate with `&limit=5000&offset=N`.

### [ ] A. India Data Portal — NFHS (BOTH rounds) ⭐⭐⭐  *(the single most important pull)*
- **URL (one call, 1,267 rows):**
  `https://ckan.indiadataportal.com/api/3/action/datastore_search?resource_id=b8ac1c23-d13f-4a91-aa4c-a056605f9115&limit=5000`
- **Save to:** `data/raw/idp_nfhs/nfhs4_5_districts.json`
- **Verify:** `result.total` ≈ 1267; each record has `district_code`, `district_name`, `year` (2014-15 and 2019-20), and fields like `wom_bld_sugar_high`, `wom_bp_mild`, `wom_obese`, `tobaco_women_15`, `hh_hlth_ins_fs`.
- **Why it matters:** has BOTH NFHS rounds → gives the chronic-risk *momentum* feature, and `district_code` for clean joins.

### [ ] B. India Data Portal — Census PCA Demography (Districts) ⭐⭐
- **resource_id:** `efefb405-bd30-4041-bd36-5e6b0d9432ff` (~188,910 rows → **paginate**)
- **Loop:** offset = 0, 5000, 10000, … until a page returns 0 records (~38 pages):
  `…datastore_search?resource_id=efefb405-bd30-4041-bd36-5e6b0d9432ff&limit=5000&offset=<N>`
- **Save to:** `data/raw/idp_pca/pca_districts_p<N>.json` (one file per page)
- **Verify:** first page `result.total` ≈ 188910; records carry `district_code`, `rural_urban`, `gender`, `age`, `population`.

### [ ] C. India Data Portal — SECC 2011 ⭐⭐
- **URL (one call, ~3,786 rows):**
  `https://ckan.indiadataportal.com/api/3/action/datastore_search?resource_id=796424c9-5eb7-4ff5-9174-7ab6b3dc4b06&limit=5000`
- **Save to:** `data/raw/idp_secc/secc_2011.json`
- **Verify:** `result.total` ≈ 3786; deprivation / landless-HH / SC-ST fields present.

### [ ] D. data.gov.in — NFHS-5 factsheet (707 districts × 109 indicators) ⭐⭐
- **Key:** use `data_gov_in.api_key` from [Credentials/DATA_GOV_IN_API_KEY.json](../Credentials/DATA_GOV_IN_API_KEY.json).
- **URL (one call):**
  `https://api.data.gov.in/resource/cf80173e-fece-439d-a0b1-6e9cb510593d?api-key=<KEY>&format=json&limit=1000`
- **Save to:** `data/raw/datagovin_nfhs5/nfhs5_factsheet_707.json`
- **Verify:** `total` = 707; fields include `Women_High_Blood_Sugar`, `Women_Elevated_BP`, `Women_Breast_Cancer`, `Health_Insurance_Scheme_Coverage`, `Out-of-Pocket_Expenditure`.
- **Note:** this copy has district **names** only (no code) → join via LGD crosswalk, or prefer A which has codes. Use D for the extra indicators A lacks (cancer, insurance, OOP).

### [ ] E. geoBoundaries — district boundaries (for maps) ⭐⭐
- **Step 1 (metadata):** open `https://www.geoboundaries.org/api/current/gbOpen/IND/ADM2/` → copy `gjDownloadURL`.
- **Step 2 (download that GeoJSON, ~735 features):** save to `data/raw/geo/india_adm2.geojson`
- **Verify:** ~735 features; each has `shapeName`, `shapeID` (LGD lineage).

### [ ] F. India Data Portal — HMIS sub-district ⭐ (optional, big + stale)
- **resource_id:** `eb0d4fba-d333-4025-a574-b0da7fd33b09` (~547,336 rows → paginate, ~110 pages)
- **Save to:** `data/raw/idp_hmis/hmis_p<N>.json`
- **⚠️ Two caveats:** data ends **~2021**, and the `date` column is malformed (month always `01`; the **day slot holds the real month** — e.g. `2019-01-08` means **Aug 2019**). Parse as year + day-as-month.
- Skip on the first pass if time-boxed; A–E are the priority.

### [ ] G. Ni-kshay — district TB (public vs private) ⭐
- **Session first:** GET `https://reports.nikshay.in/reports/tbnotification` (establishes cookie).
- **Then POST** `https://reports.nikshay.in/Home/getPublicPrivateCountDistrict`
  body (form-urlencoded): `FromDate=01/01/2024&ToDate=31/12/2024&State=<StateName>` (dates dd/mm/yyyy)
- **Loop** all 36 states/UTs by name. **Save to:** `data/raw/nikshay/tb_<state>.json`
- **Verify:** JSON array with district labels + public + private counts.
- Browser note: easiest via the page's own filters, or a `fetch()` POST in DevTools on that origin.

### [ ] H. PMJAY — empanelled hospitals (district, public/private) ⭐
- **Session:** GET `https://hospitals.pmjay.gov.in/Search/` (get `jsessionid`).
- **District list per state:** POST `…/empanelApplicationForm.htm?actionVal=GETLOCATIONS&locType=DT&locVal=<stateCensusCode>`
- **Search:** POST `https://hospitals.pmjay.gov.in/Search/empnlWorkFlow.htm` with
  `actionFlag=ViewRegisteredHosptlsNew&search=Y&applSearch=N&appReadOnly=Y&draftMenu=N&searchState=<code>&searchDistrict=<code>&searchHospType=-1&searchSpeciality=-1&searchHospName=-1&empanelmentType=-1`
- **Save to:** `data/raw/pmjay/hospitals_<state>_<district>.html` (HTML table → parse later).
- **Verify:** rows with hospital name + Public/Private tag.

### [ ] I. SHRUG — socioeconomic depth (optional)
- **Manifest:** `https://www.devdatalab.org/shrug_download/data` → pick tables → direct S3 zip links.
- **Save to:** `data/raw/shrug/`. License CC BY-NC-SA (**academic use OK** for this project; cite Dev Data Lab).

### [ ] J. DHS API — state-level covariates (optional anchor)
- **URL (no key):** `https://api.dhsprogram.com/rest/dhs/data?countryIds=IA&surveyIds=IA2020DHS&breakdown=all&perpage=5000&f=json`
- **Save to:** `data/raw/dhs/nfhs5_state.json`. **Remember:** India = **state-level only** here; use as a downscaling anchor, not district data.

---

## 4. Optional Python fallback (if browser fetching is tedious)
Run from the project root. Pulls A–E in one go (no key needed except D).
```python
import json, os, time, urllib.parse, urllib.request
CK = "https://ckan.indiadataportal.com/api/3/action/datastore_search"
def ckan(rid, out, total_guess=None):
    os.makedirs(os.path.dirname(out), exist_ok=True)
    off, allrecs = 0, []
    while True:
        u = f"{CK}?resource_id={rid}&limit=5000&offset={off}"
        d = json.load(urllib.request.urlopen(u, timeout=60))["result"]
        recs = d["records"]; allrecs += recs
        if len(recs) < 5000: break
        off += 5000; time.sleep(0.5)
    json.dump(allrecs, open(out,"w")); print(out, len(allrecs))
ckan("b8ac1c23-d13f-4a91-aa4c-a056605f9115", "data/raw/idp_nfhs/nfhs4_5_districts.json")
ckan("efefb405-bd30-4041-bd36-5e6b0d9432ff", "data/raw/idp_pca/pca_districts.json")
ckan("796424c9-5eb7-4ff5-9174-7ab6b3dc4b06", "data/raw/idp_secc/secc_2011.json")
# D: data.gov.in NFHS-5 factsheet (needs key)
KEY = json.load(open("Credentials/DATA_GOV_IN_API_KEY.json"))["data_gov_in"]["api_key"]
u = f"https://api.data.gov.in/resource/cf80173e-fece-439d-a0b1-6e9cb510593d?api-key={KEY}&format=json&limit=1000"
json.dump(json.load(urllib.request.urlopen(u, timeout=60)), open("data/raw/datagovin_nfhs5/nfhs5_factsheet_707.json","w"))
```

---

## 5. 📌 STATE — resume table (UPDATE THIS AS YOU GO)
| Step | Status | Saved to | Rows | Date / who | Notes / errors |
|---|---|---|---|---|---|
| A · IDP NFHS both rounds | ☐ todo | — | — | — | — |
| B · IDP Census PCA districts | ☐ todo | — | — | — | — |
| C · IDP SECC 2011 | ☐ todo | — | — | — | — |
| D · data.gov.in NFHS-5 factsheet | ☐ todo | — | — | — | — |
| E · geoBoundaries polygons | ☐ todo | — | — | — | — |
| F · IDP HMIS (optional) | ☐ todo | — | — | — | — |
| G · Ni-kshay TB | ☐ todo | — | — | — | — |
| H · PMJAY hospitals | ☐ todo | — | — | — | — |
| I · SHRUG (optional) | ☐ todo | — | — | — | — |
| J · DHS state (optional) | ☐ todo | — | — | — | — |

**Definition of done (first pass):** A, B, C, D, E ticked and verified = enough raw data to start the district feature matrix. F–J are enrichment.

---

## 6. START-HERE prompt (paste into a fresh Claude that has the Chrome extension)
```
You are resuming a data-scraping task with the Claude Chrome extension. Read the file
docs/SCRAPING_CHECKLIST.md in this project (/Users/hrishavmajumder/Documents/Trylitics/).
Do NOT re-plan — just execute. Rules:
- Skip everything in section 1 (org-gated / dead). I only have a personal email.
- Work section 3 top to bottom, starting at the first unchecked [ ] box in the STATE table.
- For each step: open the given URL in the browser (CKAN/data.gov.in return JSON directly),
  confirm you got real rows matching the "Verify" line, then save the raw response to the
  stated data/raw/... path.
- After each step, TICK its box and fill the STATE table row (saved-to, rows, date, notes).
- If any call errors or returns empty, STOP that step and write the exact error into the
  STATE table — do not fake data or invent a workaround.
- When A, B, C, D, E are done and verified, report back to me.
```
