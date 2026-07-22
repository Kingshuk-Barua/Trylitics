#!/usr/bin/env python3
"""
Build simplified India ADM2 (district) GeoJSON assets for the Next.js dashboard.

Outputs (all under web/public/):
  india_adm2.geojson             all districts, hard simplification, < 3 MB
  districts/<state-slug>.geojson per-state districts, lighter simplification
  districts/index.json           slug -> {state, file, districts}
  geo_name_map.json              shapeName -> district_code match report

Re-runnable end to end:  python3 web/scripts/build_geo.py
Raw downloads and intermediates are cached outside the repo (WORK_DIR).

Requires: shapely (pip3 install --user shapely), npx/mapshaper (optional but
preferred; falls back to a pure-python Douglas-Peucker implementation).
"""
from __future__ import annotations

import csv
import datetime as dt
import difflib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
PUBLIC = REPO / "web" / "public"
DISTRICTS_DIR = PUBLIC / "districts"
STATES_GEOJSON = PUBLIC / "india_states.geojson"
SCORES_CSV = REPO / "analysis" / "audit" / "_cache" / "v2" / "scores_v2.csv"

WORK_DIR = Path(
    os.environ.get("GEO_WORK_DIR")
    or (Path(tempfile.gettempdir()) / "trylitics_geo_build")
)

GB_API = "https://www.geoboundaries.org/api/current/gbOpen/IND/ADM2/"

MAX_ADM2_BYTES = 3 * 1024 * 1024
MAX_STATE_BYTES = 800 * 1024
NATIONAL_STEPS = [4.0, 3.0, 2.0, 1.5, 1.0, 0.7, 0.5, 0.3]
STATE_STEPS = [18.0, 12.0, 8.0, 5.0, 3.0, 2.0, 1.0]
KEEP_PROPS = ("shapeName", "shapeID", "state")


def log(*a):
    print(*a, file=sys.stderr, flush=True)


# --------------------------------------------------------------------------
# Step 1: download
# --------------------------------------------------------------------------
def fetch_adm2() -> Path:
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    raw = WORK_DIR / "ind_adm2_raw.geojson"
    if raw.exists() and raw.stat().st_size > 1_000_000:
        log(f"[1] using cached {raw} ({raw.stat().st_size/1e6:.1f} MB)")
        return raw
    log("[1] fetching geoBoundaries metadata")
    with urllib.request.urlopen(GB_API, timeout=120) as r:
        meta = json.load(r)
    if isinstance(meta, list):
        meta = meta[0]
    url = meta["gjDownloadURL"]
    log(f"[1] downloading {url}")
    with urllib.request.urlopen(url, timeout=1800) as r, open(raw, "wb") as f:
        shutil.copyfileobj(r, f)
    log(f"[1] saved {raw} ({raw.stat().st_size/1e6:.1f} MB)")
    return raw


# --------------------------------------------------------------------------
# Step 2: state assignment
# --------------------------------------------------------------------------
def assign_states(raw: Path):
    from shapely.geometry import shape
    from shapely.strtree import STRtree
    from shapely.prepared import prep

    log("[2] loading geometries")
    adm2 = json.loads(raw.read_text())
    states = json.loads(STATES_GEOJSON.read_text())

    state_names, state_geoms = [], []
    for f in states["features"]:
        state_names.append(f["properties"]["NAME_1"])
        state_geoms.append(shape(f["geometry"]).buffer(0))
    prepared = [prep(g) for g in state_geoms]
    tree = STRtree(state_geoms)
    centroids = [g.centroid for g in state_geoms]

    out, inferred = [], []
    for feat in adm2["features"]:
        geom = shape(feat["geometry"])
        if not geom.is_valid:
            geom = geom.buffer(0)
        pt = geom.centroid
        if not geom.contains(pt):
            pt = geom.representative_point()

        hit = None
        for idx in tree.query(pt):
            if prepared[int(idx)].contains(pt):
                hit = int(idx)
                break
        if hit is None:  # point may sit just off a coastal state polygon
            best, bestd = None, float("inf")
            for i, g in enumerate(state_geoms):
                d = g.distance(pt)
                if d < bestd:
                    best, bestd = i, d
            if bestd < 0.15:  # ~15 km tolerance -> treat as a real hit
                hit = best
            else:
                best_c, bestcd = None, float("inf")
                for i, c in enumerate(centroids):
                    d = c.distance(pt)
                    if d < bestcd:
                        best_c, bestcd = i, d
                hit = best_c
                inferred.append((feat["properties"].get("shapeName"), state_names[hit]))
                feat["properties"]["state_inferred"] = True

        props = {k: feat["properties"].get(k) for k in ("shapeName", "shapeID")}
        props["state"] = state_names[hit]
        if feat["properties"].get("state_inferred"):
            props["state_inferred"] = True
        out.append({"type": "Feature", "properties": props, "geometry": feat["geometry"]})

    log(f"[2] assigned {len(out)} districts; {len(inferred)} inferred by nearest centroid")
    for n, s in inferred:
        log(f"    inferred: {n} -> {s}")
    return {"type": "FeatureCollection", "features": out}, inferred


# --------------------------------------------------------------------------
# Step 3: simplify + write
# --------------------------------------------------------------------------
def have_mapshaper() -> bool:
    try:
        subprocess.run(["npx", "--yes", "mapshaper", "--version"],
                       capture_output=True, timeout=300, check=True)
        return True
    except Exception:
        return False


def mapshaper_simplify(src: Path, dst: Path, pct: float):
    cmd = ["npx", "--yes", "mapshaper", str(src),
           "-simplify", "visvalingam", "weighted", f"{pct}%", "keep-shapes",
           "-o", "precision=0.0001", "force", str(dst)]
    subprocess.run(cmd, check=True, capture_output=True, timeout=1800)
    return " ".join(cmd)


# ---- pure-python fallback -------------------------------------------------
def _dp(pts, tol):
    if len(pts) < 3:
        return pts
    keep = [False] * len(pts)
    keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        a, b = stack.pop()
        (x1, y1), (x2, y2) = pts[a], pts[b]
        dx, dy = x2 - x1, y2 - y1
        norm = math.hypot(dx, dy) or 1e-12
        imax, dmax = -1, 0.0
        for i in range(a + 1, b):
            x, y = pts[i]
            d = abs(dy * x - dx * y + x2 * y1 - y2 * x1) / norm
            if d > dmax:
                imax, dmax = i, d
        if imax != -1 and dmax > tol:
            keep[imax] = True
            stack.append((a, imax))
            stack.append((imax, b))
    return [p for p, k in zip(pts, keep) if k]


def _ring(ring, tol, rnd=4):
    s = _dp([tuple(p[:2]) for p in ring], tol)
    while len(s) < 4:
        s = [tuple(p[:2]) for p in ring]
        break
    s = [[round(x, rnd), round(y, rnd)] for x, y in s]
    if s[0] != s[-1]:
        s.append(s[0])
    return s


def py_simplify(fc, tol):
    def geom(g):
        t = g["type"]
        if t == "Polygon":
            return {"type": t, "coordinates": [_ring(r, tol) for r in g["coordinates"]]}
        if t == "MultiPolygon":
            return {"type": t, "coordinates":
                    [[_ring(r, tol) for r in poly] for poly in g["coordinates"]]}
        return g
    return {"type": "FeatureCollection",
            "features": [{"type": "Feature", "properties": f["properties"],
                          "geometry": geom(f["geometry"])} for f in fc["features"]]}


def slugify(name: str) -> str:
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    s = s.lower().replace("&", " and ")
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s


def write_outputs(fc, use_mapshaper: bool):
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    src = WORK_DIR / "adm2_with_state.geojson"
    slim = {"type": "FeatureCollection", "features": [
        {"type": "Feature",
         "properties": {k: f["properties"].get(k) for k in KEEP_PROPS},
         "geometry": f["geometry"]} for f in fc["features"]]}
    src.write_text(json.dumps(slim))

    national_out = PUBLIC / "india_adm2.geojson"
    used_cmd, used_pct = None, None

    if use_mapshaper:
        for pct in NATIONAL_STEPS:
            tmp = WORK_DIR / f"nat_{pct}.geojson"
            used_cmd = mapshaper_simplify(src, tmp, pct)
            size = tmp.stat().st_size
            log(f"[3] national {pct}% -> {size/1e6:.2f} MB")
            if size <= MAX_ADM2_BYTES:
                shutil.copyfile(tmp, national_out)
                used_pct = pct
                break
        else:
            raise RuntimeError("could not get india_adm2.geojson under 3 MB")
    else:
        for tol in [0.02, 0.03, 0.05, 0.08, 0.12]:
            data = py_simplify(slim, tol)
            blob = json.dumps(data, separators=(",", ":"))
            log(f"[3] national DP tol={tol} -> {len(blob)/1e6:.2f} MB")
            if len(blob) <= MAX_ADM2_BYTES:
                national_out.write_text(blob)
                used_cmd = f"python Douglas-Peucker tolerance={tol} deg, coords rounded to 4dp"
                used_pct = tol
                break
        else:
            raise RuntimeError("could not get india_adm2.geojson under 3 MB")

    # ---- per state ----
    if DISTRICTS_DIR.exists():
        shutil.rmtree(DISTRICTS_DIR)
    DISTRICTS_DIR.mkdir(parents=True)

    by_state = {}
    for f in slim["features"]:
        by_state.setdefault(f["properties"]["state"], []).append(f)

    index = {}
    for state, feats in sorted(by_state.items()):
        slug = slugify(state)
        sub = {"type": "FeatureCollection", "features": feats}
        sub_path = WORK_DIR / f"state_{slug}_src.geojson"
        sub_path.write_text(json.dumps(sub))
        dest = DISTRICTS_DIR / f"{slug}.geojson"

        if use_mapshaper:
            for pct in STATE_STEPS:
                tmp = WORK_DIR / f"state_{slug}_{pct}.geojson"
                mapshaper_simplify(sub_path, tmp, pct)
                if tmp.stat().st_size <= MAX_STATE_BYTES or pct == STATE_STEPS[-1]:
                    shutil.copyfile(tmp, dest)
                    break
        else:
            for tol in [0.004, 0.008, 0.02, 0.05]:
                blob = json.dumps(py_simplify(sub, tol), separators=(",", ":"))
                if len(blob) <= MAX_STATE_BYTES or tol == 0.05:
                    dest.write_text(blob)
                    break

        index[slug] = {"state": state, "file": f"/districts/{slug}.geojson",
                       "districts": len(feats)}
        log(f"[3] {slug}: {len(feats)} districts, {dest.stat().st_size/1024:.0f} KB")

    (DISTRICTS_DIR / "index.json").write_text(json.dumps(index, indent=2))
    return used_cmd, used_pct, index


# --------------------------------------------------------------------------
# Step 4: name matching
# --------------------------------------------------------------------------
TRAILING = ("district", "dist", "distt", "division", "zilla", "zila")


def norm(s: str) -> str:
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


def build_name_map(fc):
    records = []
    with open(SCORES_CSV, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            code = str(row["district_code"]).strip().zfill(3)
            records.append({"code": code,
                            "district_name": row["district_name"].strip(),
                            "state_name": row["state_name"].strip()})

    by_state_name, by_name = {}, {}
    for r in records:
        by_state_name.setdefault((norm(r["state_name"]), norm(r["district_name"])), []).append(r)
        by_name.setdefault(norm(r["district_name"]), []).append(r)

    state_pool = {}
    for r in records:
        state_pool.setdefault(norm(r["state_name"]), set()).add(norm(r["district_name"]))
    all_names = list(by_name)

    exact, fuzzy, unmatched_geo = {}, [], []
    matched_codes = set()

    for f in fc["features"]:
        shape_name = f["properties"]["shapeName"]
        state = f["properties"]["state"]
        key = f"{shape_name}|{state}"
        n, ns = norm(shape_name), norm(state)

        hit = by_state_name.get((ns, n)) or by_name.get(n)
        if hit:
            exact[key] = hit[0]["code"]
            matched_codes.add(hit[0]["code"])
            continue

        pool = sorted(state_pool.get(ns, set())) or all_names
        cand = difflib.get_close_matches(n, pool, n=1, cutoff=0.88)
        if not cand:
            cand = difflib.get_close_matches(n, all_names, n=1, cutoff=0.88)
        if cand:
            rec = (by_state_name.get((ns, cand[0])) or by_name.get(cand[0]))[0]
            fuzzy.append({"shape_name": shape_name, "state": state,
                          "matched_name": rec["district_name"], "code": rec["code"],
                          "score": round(difflib.SequenceMatcher(None, n, cand[0]).ratio(), 4)})
            matched_codes.add(rec["code"])
        else:
            unmatched_geo.append({"shape_name": shape_name, "state": state})

    unmatched_records = [r for r in records if r["code"] not in matched_codes]

    out = {
        "generated_at": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "exact": exact,
        "fuzzy": fuzzy,
        "unmatched_geo": unmatched_geo,
        "unmatched_records": unmatched_records,
    }
    (PUBLIC / "geo_name_map.json").write_text(json.dumps(out, indent=2))
    log(f"[4] exact={len(exact)} fuzzy={len(fuzzy)} "
        f"unmatched_geo={len(unmatched_geo)} unmatched_records={len(unmatched_records)}")
    return out


def main():
    PUBLIC.mkdir(parents=True, exist_ok=True)
    raw = fetch_adm2()
    fc, inferred = assign_states(raw)
    cmd, pct, index = write_outputs(fc, have_mapshaper())
    report = build_name_map(fc)
    log("\n=== SUMMARY ===")
    log(f"features: {len(fc['features'])}, states: {len(index)}")
    log(f"simplify: {cmd}")
    log(f"india_adm2.geojson: {(PUBLIC/'india_adm2.geojson').stat().st_size/1e6:.2f} MB")
    log(f"inferred states: {inferred}")


if __name__ == "__main__":
    main()
