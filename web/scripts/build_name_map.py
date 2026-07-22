"""Join geoBoundaries district polygons to MAI district records.

Runs standalone against the already-simplified `web/public/india_adm2.geojson`,
so re-matching does not require re-downloading 48 MB:

    python3 web/scripts/build_name_map.py

Three rules, in order, and the order is the point:

  1. ALIASES first. A curated table beats any string metric on this data,
     because the hard cases are renames (Gurgaon -> Gurugram, Allahabad ->
     Prayagraj, Mysore -> Mysuru), transliterations (Haora -> Howrah,
     Koch Bihar -> Coochbehar) and administrative re-namings (Sikkim's
     compass districts -> Gangtok/Mangan/Namchi/Gyalshing). None of those is
     recoverable from edit distance.

  2. STRICT WITHIN-STATE matching. The first version of this script fell back
     to a national name pool when a state had no hit, which produced silent
     nonsense: Sikkim's "North District" matched Delhi's "North", "Bijapur"
     in Karnataka matched Chhattisgarh's Bijapur, "Raigarh" in Maharashtra
     matched Chhattisgarh's Raigarh. A district in the wrong state is worse
     than a white polygon, because white is visibly missing and a wrong join
     is not. Cross-state matching now happens ONLY through the explicit
     enclave table below.

  3. ONE-TO-ONE. A record code may be claimed once. Fuzzy candidates are
     ranked by score and assigned greedily, so "Warangal (R)" and
     "Warangal (U)" cannot both collapse onto the same record.

Anything left over is reported in both directions and rendered white by the
app, never guessed at.
"""
import csv
import datetime as dt
import difflib
import json
import re
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PUBLIC = ROOT / "web" / "public"
ADM2 = PUBLIC / "india_adm2.geojson"
SCORES_CSV = ROOT / "analysis" / "audit" / "_cache" / "v2" / "scores_v2.csv"

TRAILING = ("district", "dist", "distt", "division", "zilla", "zila")

# Geometric state assignment is by interior point, so enclaves and coastal
# slivers land in the wrong polygon. These are the observed cases; each is a
# correction of the ASSIGNED state, not a licence to match across states.
STATE_FIX = {
    "Diu": "Dadra and Nagar Haveli and Daman and Diu",
    "Daman": "Dadra and Nagar Haveli and Daman and Diu",
    "Dadra and Nagar Haveli": "Dadra and Nagar Haveli and Daman and Diu",
    "Mahe": "Puducherry",
    "Yanam": "Puducherry",
    "Karaikal": "Puducherry",
    "Puducherry": "Puducherry",
    "Phek": "Nagaland",
    "Nandurbar": "Maharashtra",
}

# geo shapeName -> MAI district_name, scoped by normalised state.
ALIASES = {
    "andhra pradesh": {
        "sri potti sriramulu nellore": "spsr nellore",
        "kadapa ysr": "cuddapah",
        "y s r": "cuddapah",
    },
    "assam": {
        "kamrup metropolitan": "kamrup metro",
        "karbi anglong east": "karbi anglong",
        "karbi anglong west": "west karbi anglong",
        "morigaon": "marigaon",
    },
    "chhattisgarh": {
        "dakshin bastar dantewada": "dantewada",
        "uttar bastar kanker": "kanker",
        "kabeerdham": "kabirdham",
        "koriya": "korea",
    },
    "gujarat": {
        "ahmadabad": "ahmedabad",
        "aravali": "arvalli",
        "batod": "botad",
        "chhota udaipur": "chhotaudepur",
        "the dangs": "dang",
        "banas kantha": "banaskantha",
        "sabar kantha": "sabarkantha",
        "panch mahals": "panchmahal",
        "mahesana": "mehsana",
    },
    "dadra and nagar haveli": {
        "dadra and nagar haveli": "dadra and nagar haveli",
        "daman": "daman",
        "diu": "diu",
    },
    "haryana": {
        "gurgaon": "gurugram",
        "mewat": "nuh",
        "charkhi dadri": "charki dadri",
    },
    "jammu and kashmir": {
        "badgam": "budgam",
        "punch": "poonch",
        "shupiyan": "shopian",
        "bandipore": "bandipora",
        "baramula": "baramulla",
    },
    "jharkhand": {
        "purbi singhbhum": "east singhbum",
        "pashchimi singhbhum": "west singhbhum",
        "kodarma": "koderma",
        "saraikela kharsawan": "saraikela",
    },
    "karnataka": {
        "bangalore": "bengaluru urban",
        "bangalore rural": "bengaluru rural",
        "belgaum": "belagavi",
        "bellary": "ballari",
        "gulbarga": "kalaburagi",
        "mysore": "mysuru",
        "shimoga": "shivamogga",
        "tumkur": "tumakuru",
        "bijapur": "vijayapura",
        "chikmagalur": "chikkamagaluru",
        "chamrajnagar": "chamarajanagar",
    },
    "madhya pradesh": {
        "hoshangabad": "narmadapuram",
        "khandwa east nimar": "east nimar",
        "khargone west nimar": "khargone",
        "narsimhapur": "narsinghpur",
        "agar": "agar malwa",
        "east nimar khandwa": "east nimar",
    },
    "maharashtra": {
        "bid": "beed",
        "raigarh": "raigad",
        "gondiya": "gondia",
        "buldana": "buldhana",
    },
    "odisha": {
        "baudh": "boudh",
        "debagarh": "deogarh",
        "subarnapur": "sonepur",
        "anugul": "angul",
        "baleshwar": "balasore",
        "jajapur": "jajpur",
        "kendujhar": "keonjhar",
        "sundargarh": "sundergarh",
    },
    "puducherry": {
        "puducherry": "pondicherry",
    },
    "punjab": {
        "firozpur": "ferozepur",
        "muktsar": "sri muktsar sahib",
        "sahibzada ajit singh nagar": "s a s nagar",
        "shahid bhagat singh nagar": "nawanshahr",
        "tarn taran": "tarn taran",
    },
    "rajasthan": {
        "chittaurgarh": "chittorgarh",
        "dhaulpur": "dholpur",
        "jhunjhunun": "jhunjhunu",
        "ganganagar": "sri ganganagar",
    },
    "sikkim": {
        # NB these are POST-normalisation keys: "North District" loses its
        # trailing administrative noun before lookup and arrives as "north".
        "east": "gangtok",
        "north": "mangan",
        "south": "namchi",
        "west": "gyalshing",
        "east sikkim": "gangtok",
        "north sikkim": "mangan",
        "south sikkim": "namchi",
        "west sikkim": "gyalshing",
    },
    "tamil nadu": {
        "kancheepuram": "kanchipuram",
        "thoothukkudi": "tuticorin",
        "tiruchirappalli": "trichirappalli",
        "virudunagar": "virudhunagar",
    },
    "telangana": {
        "bhadradri": "bhadradri kothagudem",
        "jangaon": "jangoan",
        "jayashankar": "jayashankar bhupalapally",
        "jogulamba": "jogulamba gadwal",
        "komaram bheem": "kumuram bheem asifabad",
        "medchal": "medchal malkajgiri",
        "yadadri bhongiri": "yadadri bhuvanagiri",
        "warangal u": "hanumakonda",
        "warangal urban": "hanumakonda",
        "warangal r": "warangal",
        "warangal rural": "warangal",
        "mahabubnagar": "mahbubnagar",
        "ranga reddy": "rangareddy",
    },
    "tripura": {
        "sipahijula": "sepahijala",
        "unokoti": "unakoti",
    },
    "uttar pradesh": {
        "allahabad": "prayagraj",
        "faizabad": "ayodhya",
        "jyotiba phule nagar": "amroha",
        "mahamaya nagar": "hathras",
        "kanshiram nagar": "kasganj",
        "sant ravidas nagar bhadohi": "bhadohi",
        "sant ravidas nagar": "bhadohi",
        "bara banki": "barabanki",
        "kheri": "lakhimpur kheri",
        "rae bareli": "raebareli",
        "sant kabir nagar": "sant kabeer nagar",
        "kanpur dehat": "kanpur dehat",
        "gautam buddha nagar": "gautam buddha nagar",
    },
    "uttarakhand": {
        "garhwal": "pauri garhwal",
        "hardwar": "haridwar",
        "udham singh nagar": "udham singh nagar",
    },
    "west bengal": {
        "north twenty four parganas": "24 paraganas north",
        "south twenty four parganas": "24 paraganas south",
        "barddhaman": "purba bardhaman",
        "purba bardhaman": "purba bardhaman",
        "paschim bardhaman": "paschim bardhaman",
        "koch bihar": "coochbehar",
        "darjiling": "darjeeling",
        "dakshin dinajpur": "dinajpur dakshin",
        "uttar dinajpur": "dinajpur uttar",
        "hugli": "hooghly",
        "haora": "howrah",
        "purba medinipur": "medinipur east",
        "paschim medinipur": "medinipur west",
        "maldah": "malda",
        "puruliya": "purulia",
        "bankura": "bankura",
    },
    "himachal pradesh": {
        "lahul and spiti": "lahaul and spiti",
    },
    "bihar": {
        "purba champaran": "east champaran",
        "pashchim champaran": "west champaran",
        "kaimur bhabua": "kaimur",
        "kaimur": "kaimur",
    },
}

# Source polygons that correspond to no district at all.
GEO_DROP = {"data not available"}

STATE_ALIASES = {
    "orissa": "odisha", "pondicherry": "puducherry", "maharastra": "maharashtra",
    "uttaranchal": "uttarakhand", "nct of delhi": "delhi",
    "jammu kashmir": "jammu and kashmir",
    "andaman nicobar": "andaman and nicobar islands",
    "andaman and nicobar": "andaman and nicobar islands",
    "dadra and nagar haveli and daman and diu": "dadra and nagar haveli",
    "the dadra and nagar haveli and daman and diu": "dadra and nagar haveli",
    "daman and diu": "dadra and nagar haveli",
    "chattisgarh": "chhattisgarh", "telengana": "telangana",
}


def norm(s):
    if s is None:
        return ""
    s = unicodedata.normalize("NFKD", str(s))
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower().replace("&", " and ")
    s = re.sub(r"[^a-z0-9]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    for _ in range(2):
        for w in TRAILING:
            if s.endswith(" " + w):
                s = s[: -(len(w) + 1)].strip()
    return s


def norm_state(s):
    n = norm(s)
    if n.startswith("the "):
        n = n[4:]
    return STATE_ALIASES.get(n, n)


def load_records():
    out = []
    with open(SCORES_CSV, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            code = str(row["district_code"]).strip().zfill(3)
            out.append({"code": code,
                        "district_name": row["district_name"].strip(),
                        "state_name": row["state_name"].strip()})
    return out


def build(fc, records):
    by_state = {}
    for r in records:
        by_state.setdefault(norm_state(r["state_name"]), {})[
            norm(r["district_name"])] = r

    exact, fuzzy, unmatched_geo, dropped = {}, [], [], []
    claimed = {}                       # code -> how it was claimed
    pending = []                       # features needing the fuzzy pass

    for f in fc["features"]:
        p = f["properties"]
        shape_name = p["shapeName"]
        state = STATE_FIX.get(shape_name, p.get("state") or "")
        key = "%s|%s" % (shape_name, state)
        n, ns = norm(shape_name), norm_state(state)

        if n in GEO_DROP:
            dropped.append({"shape_name": shape_name, "state": state,
                            "reason": "placeholder polygon in the source data"})
            continue

        pool = by_state.get(ns, {})
        alias = ALIASES.get(ns, {}).get(n)
        target = alias or n
        rec = pool.get(target)
        if rec and rec["code"] not in claimed:
            exact[key] = rec["code"]
            claimed[rec["code"]] = "alias" if alias else "exact"
            continue
        pending.append((key, shape_name, state, ns, n))

    # Fuzzy pass: score every (feature, unclaimed record) pair inside the same
    # state, then assign greedily from the best score down. Greedy on a sorted
    # list is what makes the assignment one-to-one.
    cands = []
    for key, shape_name, state, ns, n in pending:
        for rn, rec in by_state.get(ns, {}).items():
            if rec["code"] in claimed:
                continue
            score = difflib.SequenceMatcher(None, n, rn).ratio()
            if score >= 0.86:
                cands.append((score, key, shape_name, state, rec))
    cands.sort(key=lambda t: -t[0])
    taken_keys = set()
    for score, key, shape_name, state, rec in cands:
        if key in taken_keys or rec["code"] in claimed:
            continue
        fuzzy.append({"shape_name": shape_name, "state": state,
                      "matched_name": rec["district_name"],
                      "code": rec["code"], "score": round(score, 4)})
        exact[key] = rec["code"]
        claimed[rec["code"]] = "fuzzy"
        taken_keys.add(key)

    for key, shape_name, state, ns, n in pending:
        if key not in taken_keys:
            unmatched_geo.append({"shape_name": shape_name, "state": state})

    unmatched_records = [
        {"code": r["code"], "district_name": r["district_name"],
         "state_name": r["state_name"]}
        for r in records if r["code"] not in claimed]

    return {
        "generated_at": dt.datetime.now(dt.timezone.utc).replace(
            microsecond=0).isoformat().replace("+00:00", "Z"),
        "method": ("alias table -> strict within-state exact -> within-state "
                   "fuzzy (difflib >= 0.86, greedy one-to-one). No national "
                   "fallback: a cross-state match is a silent error, an "
                   "unmatched polygon is a visible one."),
        "counts": {"features": len(fc["features"]), "records": len(records),
                   "matched": len(exact), "fuzzy": len(fuzzy),
                   "dropped": len(dropped),
                   "unmatched_geo": len(unmatched_geo),
                   "unmatched_records": len(unmatched_records)},
        "exact": exact,
        "fuzzy": fuzzy,
        "dropped": dropped,
        "unmatched_geo": unmatched_geo,
        "unmatched_records": unmatched_records,
    }


def strip_dropped(fc, dropped):
    """Remove placeholder polygons from the published geojson.

    `DATA NOT AVAILABLE` is a 22.9-square-degree polygon in the geoBoundaries
    source — larger than any real district — that spans most of northern India.
    Rendered as an unmatched feature it paints the entire country white and the
    choropleth looks broken while every underlying fill is correct. It is not
    a district and must not reach the map.
    """
    names = {d["shape_name"] for d in dropped}
    if not names:
        return 0
    before = len(fc["features"])
    fc["features"] = [
        f for f in fc["features"]
        if f["properties"].get("shapeName") not in names
    ]
    removed = before - len(fc["features"])
    if removed:
        ADM2.write_text(json.dumps(fc, separators=(",", ":")))
    return removed


def main():
    fc = json.loads(ADM2.read_text())
    records = load_records()
    out = build(fc, records)
    removed = strip_dropped(fc, out["dropped"])
    if removed:
        print("stripped %d placeholder polygon(s) from %s" % (removed, ADM2.name))
        out["counts"]["features"] -= removed
    (PUBLIC / "geo_name_map.json").write_text(json.dumps(out, indent=1))
    c = out["counts"]
    print("features %(features)d | records %(records)d" % c)
    print("  matched        %(matched)d  (of which fuzzy %(fuzzy)d)" % c)
    print("  dropped        %(dropped)d" % c)
    print("  unmatched geo  %(unmatched_geo)d" % c)
    print("  unmatched recs %(unmatched_records)d" % c)
    print("\nfuzzy matches (audit these):")
    for f in sorted(out["fuzzy"], key=lambda x: x["score"]):
        print("  %.3f  %-34s %-18s -> %s"
              % (f["score"], f["shape_name"], f["state"], f["matched_name"]))
    return out


if __name__ == "__main__":
    main()
