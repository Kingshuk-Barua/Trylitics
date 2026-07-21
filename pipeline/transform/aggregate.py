"""District-level aggregation: raw records -> Firestore doc payloads.

Only AGGREGATES go to Firestore (~700 docs/collection); raw rows stay local
(design doc §6.3-6.4; Spark tier ~20k writes/day).

Every aggregator returns {collection_name: {doc_id: doc_dict}}.
Doc ids are strings. Aggregators must not invent values — anything derived
carries a `method` note.
"""
import re
from datetime import datetime, timezone

_NAN = {"nan", "none", "", "null"}


def _now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def slug(name):
    return re.sub(r"[^a-z0-9]+", "_", str(name).lower()).strip("_")


def is_nan(v):
    return v is None or str(v).strip().lower() in _NAN


def _num(v):
    if is_nan(v):
        return None
    try:
        f = float(v)
        return int(f) if f == int(f) else f
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# A. IDP NFHS-4 + NFHS-5  (1,267 rows, 111 fields, district_code + both rounds)
# ---------------------------------------------------------------------------
class NfhsAgg(object):
    """-> districts/{code} (master profile) + district_indicators/{code}
    with per-round NFHS indicator maps (the momentum feature)."""

    META = {"_id", "id", "year", "state_name", "state_code",
            "district_name", "district_code"}

    def __init__(self):
        self.districts = {}
        self.indicators = {}

    def add(self, records):
        for r in records:
            code = str(r.get("district_code", "")).strip()
            if not code or is_nan(code):
                continue
            round_key = slug(r.get("year", "unknown"))
            d = self.districts.setdefault(code, {
                "lgd_or_source_code": code,
                "district_name": r.get("district_name"),
                "state_name": r.get("state_name"),
                "state_code": str(r.get("state_code", "")),
                "source_id": "idp_nfhs",
                "updated_at": _now_iso(),
            })
            ind = self.indicators.setdefault(code, {
                "district_name": r.get("district_name"),
                "state_name": r.get("state_name"),
                "nfhs": {},
                "source_id": "idp_nfhs",
                "updated_at": _now_iso(),
            })
            vals = {}
            for k, v in r.items():
                if k in self.META:
                    continue
                n = _num(v)
                if n is not None:
                    vals[k] = n
            ind["nfhs"][round_key] = vals
            d["nfhs_rounds"] = sorted(set(d.get("nfhs_rounds", [])) | {round_key})

    def result(self):
        return {"districts": self.districts,
                "district_indicators": self.indicators}


# ---------------------------------------------------------------------------
# B. IDP Census PCA (~188,910 long-format rows -> per-district totals)
#
# Row semantics (verified against the full 188,910-row pull 2026-07-15):
# each row is ONE cut: the columns among (age, social_group, literacy,
# working_status, worker_type, occupation) that are NOT 'nan' define it;
# rural_urban + level + gender are always set. There are NO pure-total rows —
# each cut instead carries an explicit 'Total' member. We keep only:
#   * social_group == 'Total'            -> total population
#   * literacy == 'Literate'             -> literate population
#   * age == '0_To_6_Years'              -> population 0-6
# District codes are IDP's current-district codes (728 seen, > Census 640).
# Levels seen: Village/Town/Ward — Town and Ward are the SAME urban population
# at two granularities (verified identical for Kupwara), so we take ONE level
# per (district, rural_urban, gender): preference District > Village > Town >
# Ward. Note: totals run ~3% under the published Census 2011 abstracts
# (boundary vintage / coverage of the IDP mirror) — recorded, not corrected.
# ---------------------------------------------------------------------------
class PcaAgg(object):
    CUTS = ("age", "social_group", "literacy", "working_status",
            "worker_type", "occupation")

    def __init__(self):
        # {(code, ru, level, gender, metric): population_sum}
        self.buckets = {}
        self.names = {}
        self.levels_seen = set()

    def _metric(self, r):
        active = [c for c in self.CUTS if not is_nan(r.get(c))]
        if active == ["social_group"] and str(r["social_group"]).lower() == "total":
            return "pop"
        if active == ["literacy"] and str(r["literacy"]).lower() == "literate":
            return "literate"
        if active == ["age"] and "0_to_6" in str(r["age"]).lower():
            return "pop_0_6"
        return None  # a cut we don't aggregate in v1

    def add(self, records):
        for r in records:
            code = str(r.get("district_code", "")).strip()
            if not code or is_nan(code):
                continue
            metric = self._metric(r)
            if metric is None:
                continue
            pop = _num(r.get("population"))
            if pop is None:
                continue
            ru = str(r.get("rural_urban", "")).strip() or "Unknown"
            level = str(r.get("level", "")).strip() or "Unknown"
            gender = str(r.get("gender", "")).strip() or "Unknown"
            self.levels_seen.add(level)
            key = (code, ru, level, gender, metric)
            self.buckets[key] = self.buckets.get(key, 0) + pop
            if code not in self.names:
                self.names[code] = (r.get("district_name"),
                                    r.get("state_name"),
                                    str(r.get("state_code", "")))

    LEVEL_PREF = ("District", "Village", "Town", "Ward")

    def result(self):
        # group candidate levels per (code, ru, gender, metric)
        grouped = {}
        for (code, ru, level, gender, metric), pop in self.buckets.items():
            grouped.setdefault((code, ru, gender, metric), {})[level] = pop
        docs = {}
        for (code, ru, gender, metric), by_level in grouped.items():
            pick = next((by_level[l] for l in self.LEVEL_PREF if l in by_level),
                        None)
            if pick is None:  # unknown level name — take max, never sum dupes
                pick = max(by_level.values())
            d = docs.setdefault(code, {})
            k = "{}_{}_{}".format(metric, slug(ru), slug(gender))
            d[k] = d.get(k, 0) + pick
        out = {}
        for code, sums in docs.items():
            name, state, state_code = self.names.get(code, (None, None, None))
            doc = {"district_name": name, "state_name": state,
                   "state_code": state_code, "census_year": 2011,
                   "source_id": "idp_pca",
                   "method": ("one level per rural_urban side (pref {}); "
                              "levels seen: {}".format(
                                  ">".join(self.LEVEL_PREF),
                                  ",".join(sorted(self.levels_seen)))),
                   "updated_at": _now_iso()}
            doc.update(sums)
            # convenience: overall totals (rural+urban, gender=Total)
            tot = sum(v for k, v in sums.items()
                      if k.startswith("pop_") and k.endswith("_total")
                      and not k.startswith("pop_0_6"))
            if tot:
                doc["population_2011_total"] = tot
            out[code] = doc
        return {"census_pca": out}


# ---------------------------------------------------------------------------
# C. IDP SECC 2011 (~3,786 rows = ~6 category rows per district)
# ---------------------------------------------------------------------------
class SeccAgg(object):
    META = {"_id", "id", "state_name", "state_code", "district_name",
            "district_code", "category"}

    def __init__(self):
        self.docs = {}

    def add(self, records):
        for r in records:
            code = str(r.get("district_code", "")).strip()
            if not code or is_nan(code):
                continue
            d = self.docs.setdefault(code, {
                "district_name": r.get("district_name"),
                "state_name": r.get("state_name"),
                "state_code": str(r.get("state_code", "")),
                "categories": {},
                "source_id": "idp_secc",
                "updated_at": _now_iso(),
            })
            cat = slug(r.get("category", "unknown"))
            d["categories"][cat] = {
                k: _num(v) for k, v in r.items()
                if k not in self.META and _num(v) is not None
            }

    def result(self):
        return {"secc": self.docs}


# ---------------------------------------------------------------------------
# D. data.gov.in NFHS-5 factsheet (707 districts, names only — no code)
# ---------------------------------------------------------------------------
def agg_datagovin_nfhs5(records):
    docs = {}
    for r in records:
        # exact field names verified against the live payload 2026-07-16;
        # districts repeat across states (Aurangabad, Bilaspur, Hamirpur…),
        # so the state MUST be part of the doc id
        state = r.get("State_UT")
        district = r.get("District_Names")
        if not state or not district:
            raise ValueError(
                "datagovin_nfhs5 schema changed: State_UT/District_Names "
                "missing from record keys {}".format(list(r)[:6]))
        doc_id = slug("{}__{}".format(state, district))
        if doc_id in docs:
            raise ValueError("datagovin_nfhs5 doc id collision: {}".format(
                doc_id))
        doc = {"district_name_text": district, "state_name": state,
               "join_note": "names only — join via LGD crosswalk (design doc §6.2)",
               "source_id": "datagovin_nfhs5", "updated_at": _now_iso()}
        for k, v in r.items():
            n = _num(v)
            if n is not None:
                doc[slug(k)] = n
        docs[doc_id] = doc
    return {"nfhs5_factsheet": docs}


def get_ckan_aggregator(source_id):
    return {
        "idp_nfhs": NfhsAgg,
        "idp_pca": PcaAgg,
        "idp_secc": SeccAgg,
    }.get(source_id, lambda: None)()
