# analysis/audit — evidence for docs/MAI_AUDIT_FINDINGS.md

Read-only audit scripts. **Nothing here writes to Firestore.**

## Running

```bash
cd /path/to/Trylitics
pip3 install -r requirements.txt          # needs firebase-admin, pandas, scipy, sklearn
python3 analysis/audit/00_pull_firestore.py        # snapshot -> _cache/ (network, read-only)
python3 analysis/audit/01_profile_collections.py   # per-collection schema + coverage + stats
python3 analysis/audit/02_rebuild_index.py         # faithful rebuild; prints fidelity vs published
python3 analysis/audit/03_audit_checks.py          # the quantitative core
python3 analysis/audit/04_data_quality.py          # source-data probes + robustness re-run
python3 analysis/audit/05_population_and_factsheet.py
python3 analysis/audit/06_business_metrics.py      # decile lift, coverage curve, wealth-proxy test
```

`00_` needs credentials (`.env` or `Credentials/Firebase_Service_Account.json`,
loaded via `pipeline/config.py`). Everything after it reads only `_cache/` and
runs offline.

## What each script establishes

| script | findings it evidences |
|---|---|
| `01_profile_collections` | collection counts, field coverage, descriptive stats for all 10 collections |
| `02_rebuild_index` | rebuild fidelity (Spearman 0.99959 vs published); crosswalk match counts; coverage gate; imputation totals |
| `03_audit_checks` | C-01…C-08, M-01…M-03, M-07, M-08, M-15; Cronbach α, KMO/Bartlett, VIF, three-index correlations |
| `04_data_quality` | C-04, C-05, M-09, M-10, M-11; robustness re-run under method swaps; indicator gaps vs the brief |
| `05_population_and_factsheet` | C-03, C-04, M-10 in detail |
| `06_business_metrics` | C-01 (decile lift, coverage-vs-cost), M-03 (wealth-proxy residual test), spatial autocorrelation |

`_cache/` is a local snapshot and is safe to delete; re-run `00_` to rebuild it.
