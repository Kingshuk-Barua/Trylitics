"""Profile every cached Firestore collection: counts, field schema, coverage,
descriptive stats. Reads only analysis/audit/_cache (no network).

    python3 analysis/audit/01_profile_collections.py
"""
import json
import pickle
from pathlib import Path

import numpy as np
import pandas as pd

CACHE = Path(__file__).resolve().parent / "_cache"
pd.set_option("display.width", 200)
pd.set_option("display.max_columns", 40)
pd.set_option("display.max_rows", 200)


def load(name):
    with open(CACHE / (name + ".pkl"), "rb") as f:
        return pickle.load(f)


def flatten(d, prefix=""):
    """One level of dotted flattening; dict-of-dict maps become <k>.* counts."""
    out = {}
    for k, v in (d or {}).items():
        key = prefix + k
        if isinstance(v, dict):
            out[key + ".{}"] = len(v)
            for kk, vv in v.items():
                if isinstance(vv, dict):
                    out[key + ".*." + "{}"] = len(vv)
                    break
        elif isinstance(v, list):
            out[key + "[]"] = len(v)
        else:
            out[key] = v
    return out


def profile(name):
    docs = load(name)
    rows = [flatten(d) for d in docs.values()]
    df = pd.DataFrame(rows, index=list(docs))
    print("\n" + "=" * 100)
    print("COLLECTION %s  — %d docs, %d distinct top-level fields"
          % (name, len(docs), df.shape[1]))
    print("=" * 100)
    cov = df.notna().mean().mul(100).round(1)
    num = df.select_dtypes(include=[np.number])
    summ = pd.DataFrame({"coverage_%": cov})
    if not num.empty:
        desc = num.describe().T[["mean", "std", "min", "50%", "max"]]
        summ = summ.join(desc)
    summ["dtype"] = df.dtypes.astype(str)
    print(summ.sort_values("coverage_%").round(3).to_string())
    return docs, df


if __name__ == "__main__":
    manifest = json.load(open(CACHE / "manifest.json"))
    for name in manifest:
        try:
            profile(name)
        except Exception as e:  # noqa: BLE001 - keep profiling the rest
            print("\n!! %s profile failed: %s: %s" % (name, type(e).__name__, e))
