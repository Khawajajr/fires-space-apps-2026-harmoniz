"""Build web/data/countries.geojson, the offline basemap, from Natural Earth admin-0 (public domain).

    python web/tools/build_basemap.py [countries.json]

Source: gods-eye-view's curated copy of ne_10m_admin_0_countries (delta-encoded integer rings; see its
natural_earth/README.md). Outer rings only, rounded to 0.01° and thinned, which is plenty for a country-scale map.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "gods-eye-view" / "src" / "data" / "local_data" / "natural_earth" / "countries.json"
OUT = ROOT / "web" / "data" / "countries.geojson"


def decode_ring(ring: list[int], scale: float) -> list[list[float]]:
    lon, lat = ring[0], ring[1]
    pts = [(lon, lat)]
    for i in range(2, len(ring), 2):
        lon, lat = lon + ring[i], lat + ring[i + 1]
        pts.append((lon, lat))
    out = []
    for x, y in pts:
        p = [round(x * scale, 2), round(y * scale, 2)]
        if not out or p != out[-1]:
            out.append(p)
    if len(out) >= 3:
        out.append(out[0])   # GeoJSON rings are closed
    return out


def main(src: str = str(SRC)) -> None:
    data = json.loads(Path(src).read_text(encoding="utf-8"))
    features = []
    for f in data["features"]:
        scale = 10 ** -f.get("d", data["meta"]["decimals"])
        polys = [[decode_ring(part[0], scale)] for part in f["polygons"]]
        polys = [p for p in polys if len(p[0]) >= 4]
        if polys:
            features.append({"type": "Feature", "properties": {"name": f["name"], "iso": f.get("iso")},
                             "geometry": {"type": "MultiPolygon", "coordinates": polys}})
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"type": "FeatureCollection",
                               "attribution": "Made with Natural Earth (public domain), ne_10m_admin_0_countries",
                               "features": features}, separators=(",", ":")))
    print(f"wrote {OUT} ({OUT.stat().st_size / 1e3:.0f} kB, {len(features)} countries)")


if __name__ == "__main__":
    main(*sys.argv[1:])
