"""Central configuration for the Trilytics MAI data pipeline.

Source registry, cadences, verification expectations, paths, credentials.
See docs/PIPELINE_CHECKLIST.md for the human-readable work log and
docs/SCRAPING_CHECKLIST.md for the original source research.

Credentials are read from the environment first (a local .env is auto-loaded —
see .env.example), falling back to the git-ignored Credentials/ folder. This
lets the pipeline run on any machine or CI runner with no local files present.

Environment variables (all optional — see .env.example for the full list):
  FIREBASE_SERVICE_ACCOUNT_JSON   full Firebase Admin SDK key JSON (or base64)
  FIREBASE_CREDENTIALS_PATH       ...or a path to that key file
  GOOGLE_SERVICE_ACCOUNT_JSON     full GCP (Sheets/Drive) service-account JSON
  DATA_GOV_IN_API_KEY             data.gov.in key (source D)
  GOOGLE_SHEET_API_KEY            Google API key for read-only Sheets access
  GOOGLE_SHEET_LINK               working spreadsheet URL
  PMJAY_STATE_LIMIT               test PMJAY on the first N states only
  TRILYTICS_ENV_FILE              override the .env location
  TRILYTICS_CREDENTIALS_DIR       override the fallback Credentials/ folder
"""
import base64
import json
import os
from collections import OrderedDict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# .env autoloading — dependency-free so it works on any machine before any
# `pip install`. A local .env (project root, or TRILYTICS_ENV_FILE) is loaded
# on import; real environment variables always take precedence over it.
# ---------------------------------------------------------------------------
def load_dotenv(path=None):
    """Minimal .env parser. Supports `KEY=value`, `export KEY=value`,
    `# comments`, blank lines, and single/double-quoted values. Single-quoted
    values are kept verbatim (so a JSON blob's \\n escapes survive intact to
    json.loads); double-quoted values expand \\n \\t \\" \\\\. Variables already
    present in the real environment are never overwritten."""
    path = Path(path or os.environ.get("TRILYTICS_ENV_FILE") or ROOT / ".env")
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].lstrip()
        if "=" not in line:
            continue
        key, val = line.split("=", 1)
        key, val = key.strip(), val.strip()
        if not key or key in os.environ:
            continue
        if len(val) >= 2 and val[0] == val[-1] and val[0] in ("'", '"'):
            quote, val = val[0], val[1:-1]
            if quote == '"':
                val = (val.replace("\\n", "\n").replace("\\t", "\t")
                          .replace('\\"', '"').replace("\\\\", "\\"))
        os.environ[key] = val


load_dotenv()

DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
INTERIM_DIR = DATA_DIR / "interim"
STATE_DIR = DATA_DIR / "state"
STATE_FILE = STATE_DIR / "pipeline_state.json"
LOG_DIR = ROOT / "logs"
CHECKLIST_FILE = ROOT / "docs" / "PIPELINE_CHECKLIST.md"

# Local fallback store — consulted only when a value is absent from the
# environment. Git-ignored and fully optional on a fresh machine.
CREDENTIALS_DIR = Path(
    os.environ.get("TRILYTICS_CREDENTIALS_DIR") or ROOT / "Credentials")


def _load_json_file(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _service_account(env_json, path_vars, fallback_filename):
    """Resolve a service-account dict, in priority order:
      1. <env_json>          full JSON (or base64 of it) in the environment
      2. any of path_vars    a path to a service-account .json file
      3. Credentials/<fallback_filename>
    Returns a dict usable with firebase_admin / google-auth Certificate()."""
    blob = os.environ.get(env_json)
    if blob and blob.strip():
        blob = blob.strip()
        if not blob.startswith("{"):          # tolerate base64-encoded JSON
            blob = base64.b64decode(blob).decode("utf-8")
        return json.loads(blob)
    for var in path_vars:
        p = os.environ.get(var)
        if p and p.strip():
            return _load_json_file(Path(p).expanduser())
    return _load_json_file(CREDENTIALS_DIR / fallback_filename)


def firebase_service_account():
    """Firebase Admin SDK service-account dict (project medicine-attractive-index).
    Env FIREBASE_SERVICE_ACCOUNT_JSON, or a path in FIREBASE_CREDENTIALS_PATH /
    TRILYTICS_FIREBASE_CREDENTIALS; else Credentials/Firebase_Service_Account.json."""
    return _service_account(
        "FIREBASE_SERVICE_ACCOUNT_JSON",
        ("FIREBASE_CREDENTIALS_PATH", "TRILYTICS_FIREBASE_CREDENTIALS"),
        "Firebase_Service_Account.json")


def firebase_project_id():
    """Optional explicit project id (else inferred from the service account)."""
    pid = os.environ.get("FIREBASE_PROJECT_ID")
    return pid.strip() if pid and pid.strip() else None


def google_service_account():
    """GCP service-account dict for the optional Google Sheets / Drive layer.
    Env GOOGLE_SERVICE_ACCOUNT_JSON, or a path in GOOGLE_APPLICATION_CREDENTIALS;
    else Credentials/Google_Service_Account_Credentials.json."""
    return _service_account(
        "GOOGLE_SERVICE_ACCOUNT_JSON",
        ("GOOGLE_APPLICATION_CREDENTIALS",),
        "Google_Service_Account_Credentials.json")


def data_gov_in_api_key():
    """Platform-wide data.gov.in key (verified working platform-wide).
    Env DATA_GOV_IN_API_KEY wins; else Credentials/DATA_GOV_IN_API_KEY.json."""
    env = os.environ.get("DATA_GOV_IN_API_KEY")
    if env and env.strip():
        return env.strip()
    return _load_json_file(
        CREDENTIALS_DIR / "DATA_GOV_IN_API_KEY.json")["data_gov_in"]["api_key"]


def google_sheet_api_key():
    """Google API key for read-only Sheets access (optional curation layer).
    Env GOOGLE_SHEET_API_KEY; else Credentials/Google_Sheet_Api.json."""
    env = os.environ.get("GOOGLE_SHEET_API_KEY")
    if env and env.strip():
        return env.strip()
    return _load_json_file(
        CREDENTIALS_DIR / "Google_Sheet_Api.json")["Google_Sheet_Api"]


def google_sheet_link():
    """Working Google Sheet URL (optional staging layer).
    Env GOOGLE_SHEET_LINK; else Credentials/Google_Sheet_link.json."""
    env = os.environ.get("GOOGLE_SHEET_LINK")
    if env and env.strip():
        return env.strip()
    return _load_json_file(
        CREDENTIALS_DIR / "Google_Sheet_link.json")["Google_Sheet_link"]


# Firestore Spark free tier allows ~20k writes/day; keep headroom.
FIRESTORE_DAILY_WRITE_CAP = int(
    os.environ.get("FIRESTORE_DAILY_WRITE_CAP") or 15000)

USER_AGENT = os.environ.get("TRILYTICS_USER_AGENT") or (
    "TrilyticsMAI-pipeline/1.0 (academic student project; district health index; "
    "contact: hrishavmajumder23@gmail.com)"
)

CKAN_BASE = "https://ckan.indiadataportal.com/api/3/action/datastore_search"
CKAN_PAGE_SIZE = 5000

DAEMON_TICK_SECONDS = 60


# ---------------------------------------------------------------------------
# Source registry.
#   step        letter in SCRAPING_CHECKLIST.md §3
#   kind        which fetcher module handles it
#   cadence_h   re-fetch cadence in hours (static sources: re-verify daily/weekly)
#   expect      verification bounds — fetch FAILS (no publish) outside them
#   priority    run order (1 = first)
# ---------------------------------------------------------------------------
SOURCES = OrderedDict([
    ("idp_nfhs", {
        "step": "A", "kind": "ckan", "priority": 1, "cadence_h": 24,
        "resource_id": "b8ac1c23-d13f-4a91-aa4c-a056605f9115",
        "expect_total": (1200, 1350),
        "required_fields": ["district_code", "district_name", "year"],
        "raw_name": "idp_nfhs",
        "note": "NFHS-4 + NFHS-5 district rows with district_code. Core source.",
    }),
    ("datagovin_nfhs5", {
        "step": "D", "kind": "datagovin", "priority": 2, "cadence_h": 24,
        "resource_id": "cf80173e-fece-439d-a0b1-6e9cb510593d",
        "expect_total": (700, 720),
        "raw_name": "datagovin_nfhs5",
        "note": "707 districts x 109 indicators; district NAMES only (no code).",
    }),
    ("idp_secc", {
        "step": "C", "kind": "ckan", "priority": 3, "cadence_h": 24,
        "resource_id": "796424c9-5eb7-4ff5-9174-7ab6b3dc4b06",
        "expect_total": (3600, 4000),
        "required_fields": ["district_code"],
        "raw_name": "idp_secc",
        "note": "SECC 2011 deprivation.",
    }),
    ("geoboundaries", {
        "step": "E", "kind": "geoboundaries", "priority": 4, "cadence_h": 168,
        "meta_url": "https://www.geoboundaries.org/api/current/gbOpen/IND/ADM2/",
        "expect_features": (700, 800),
        "raw_name": "geo",
        "note": "District polygons for the choropleth. Stays local + Hosting public/.",
    }),
    ("nikshay_tb", {
        "step": "G", "kind": "nikshay", "priority": 5, "cadence_h": 1,
        "page_url": "https://reports.nikshay.in/reports/tbnotification",
        "post_url": "https://reports.nikshay.in/Home/getPublicPrivateCountDistrict",
        "raw_name": "nikshay",
        "note": "The one genuinely LIVE source: current-year district TB notifications.",
    }),
    ("idp_pca", {
        "step": "B", "kind": "ckan", "priority": 6, "cadence_h": 168,
        "resource_id": "efefb405-bd30-4041-bd36-5e6b0d9432ff",
        "expect_total": (180000, 200000),
        "required_fields": ["district_code"],
        "raw_name": "idp_pca",
        "heavy": True, "gzip_pages": True,
        "note": "Census PCA 2011, ~188k rows, ~38 pages. Static — weekly re-verify.",
    }),
    ("pmjay_hospitals", {
        "step": "H", "kind": "pmjay", "priority": 7, "cadence_h": 24,
        "session_url": "https://hospitals.pmjay.gov.in/Search/",
        "locations_url": "https://hospitals.pmjay.gov.in/Search/empanelApplicationForm.htm",
        "search_url": "https://hospitals.pmjay.gov.in/Search/empnlWorkFlow.htm",
        "raw_name": "pmjay",
        "note": "Empanelled hospitals, Public/Private per district. HTML scrape.",
    }),
    ("idp_hmis", {
        "step": "F", "kind": "ckan", "priority": 8, "cadence_h": 168,
        "resource_id": "eb0d4fba-d333-4025-a574-b0da7fd33b09",
        "expect_total": (500000, 600000),
        "raw_name": "idp_hmis",
        "heavy": True, "raw_only": True, "gzip_pages": True,
        "resume": True, "hash_mode": "total",
        "note": "HMIS sub-district ~547k rows (~6GB raw -> ~230MB gzipped); "
                "stale to ~2021; date col malformed (day slot holds real "
                "month). RAW ONLY in v1 — no aggregation yet.",
    }),
    ("dhs_state", {
        "step": "J", "kind": "dhs", "priority": 9, "cadence_h": 168,
        "url": ("https://api.dhsprogram.com/rest/dhs/data?countryIds=IA"
                "&surveyIds=IA2020DHS&breakdown=all&perpage=5000&f=json"),
        "raw_name": "dhs",
        "raw_only": True,
        "note": "STATE-level anchor only (India has no district rows in DHS API).",
    }),
    ("shrug", {
        "step": "I", "kind": "shrug", "priority": 10, "cadence_h": 168,
        # Fill with direct zip URLs picked from https://www.devdatalab.org/shrug_download/
        # Empty list => step reports SKIPPED_MANUAL (a human must pick tables).
        "download_urls": [],
        "raw_name": "shrug",
        "raw_only": True,
        "note": "Optional. CC BY-NC-SA — academic OK, cite Dev Data Lab.",
    }),
])

# Ni-kshay expects plain state display names. Verified live 2026-07-15:
# 'Jammu & Kashmir' style ampersands work; the merged 'Dadra & Nagar Haveli
# and Daman & Diu' UT is NOT accepted under any tested spelling (returns 0
# districts) — kept here so the failure stays visible in the state table.
NIKSHAY_STATES = [
    "Andaman & Nicobar Islands", "Andhra Pradesh", "Arunachal Pradesh", "Assam",
    "Bihar", "Chandigarh", "Chhattisgarh", "Dadra & Nagar Haveli", "Daman & Diu",
    "Delhi", "Goa", "Gujarat", "Haryana", "Himachal Pradesh", "Jammu & Kashmir",
    "Jharkhand", "Karnataka", "Kerala", "Ladakh", "Lakshadweep", "Madhya Pradesh",
    "Maharashtra", "Manipur", "Meghalaya", "Mizoram", "Nagaland", "Odisha",
    "Puducherry", "Punjab", "Rajasthan", "Sikkim", "Tamil Nadu", "Telangana",
    "Tripura", "Uttar Pradesh", "Uttarakhand", "West Bengal",
]


def ensure_dirs():
    for d in (RAW_DIR, INTERIM_DIR, STATE_DIR, LOG_DIR):
        d.mkdir(parents=True, exist_ok=True)
