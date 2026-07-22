"""Rewind polygon rings to d3-geo's spherical winding order.

Symptom this fixes: every district polygon renders as a shape thousands of
units across, so the last-drawn one paints over the entire map and the
choropleth appears blank white — while the DOM shows 691 correctly coloured
paths and every join is fine.

Cause: d3-geo clips on the SPHERE, not on the plane, and its convention is the
INVERSE of RFC 7946 — d3 wants an exterior ring wound CLOCKWISE and reads a
counter-clockwise one as "the whole globe except this shape". geoBoundaries
ships RFC-compliant counter-clockwise rings, so every district projects to the
same sphere-sized bounds and the last one drawn paints over the map.

Measured against the reference layer already in this project:
`india_states.geojson` renders correctly and its exterior rings have a signed
area of -6.26 (clockwise); the untouched ADM2 rings were +0.42
(counter-clockwise). That comparison is what settled the direction, rather
than trusting either spec.

Idempotent — re-running on a corrected file changes nothing.

    python3 web/scripts/fix_winding.py [path.geojson ...]
"""
import glob
import json
import sys
from pathlib import Path

PUBLIC = Path(__file__).resolve().parents[1] / "public"


def signed_area(ring):
    """Shoelace. Positive is counter-clockwise in lon/lat order."""
    s = 0.0
    for i in range(len(ring) - 1):
        x1, y1 = ring[i][0], ring[i][1]
        x2, y2 = ring[i + 1][0], ring[i + 1][1]
        s += x1 * y2 - x2 * y1
    return s / 2.0


def fix_polygon(rings):
    out = []
    for i, ring in enumerate(rings):
        a = signed_area(ring)
        ccw = a > 0
        want_ccw = i != 0            # d3: exterior clockwise, holes ccw
        out.append(ring[::-1] if ccw != want_ccw else ring)
    return out


def fix_geometry(geom):
    if geom is None:
        return 0
    t = geom.get("type")
    if t == "Polygon":
        before = json.dumps(geom["coordinates"])
        geom["coordinates"] = fix_polygon(geom["coordinates"])
        return int(json.dumps(geom["coordinates"]) != before)
    if t == "MultiPolygon":
        n = 0
        fixed = []
        for poly in geom["coordinates"]:
            before = json.dumps(poly)
            new = fix_polygon(poly)
            n += int(json.dumps(new) != before)
            fixed.append(new)
        geom["coordinates"] = fixed
        return n
    if t == "GeometryCollection":
        return sum(fix_geometry(g) for g in geom.get("geometries", []))
    return 0


def fix_file(path):
    fc = json.loads(Path(path).read_text())
    n = sum(fix_geometry(f.get("geometry")) for f in fc.get("features", []))
    if n:
        Path(path).write_text(json.dumps(fc, separators=(",", ":")))
    print("  %-46s %4d ring set(s) rewound" % (Path(path).name, n))
    return n


def main():
    targets = sys.argv[1:] or (
        [str(PUBLIC / "india_adm2.geojson")]
        + sorted(glob.glob(str(PUBLIC / "districts" / "*.geojson")))
    )
    print("rewinding for d3-geo (exterior CW, holes CCW):")
    total = sum(fix_file(t) for t in targets)
    print("total: %d" % total)


if __name__ == "__main__":
    main()
