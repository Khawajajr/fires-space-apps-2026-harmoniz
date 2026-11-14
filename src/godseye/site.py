"""
`godseye build-site`: a static snapshot of the calendar app in site/, for judges who can't run our PC.

The real API runs in-process (FastAPI TestClient on the same data) and every answer the app asks for on the named
areas is saved as JSON, in English and Arabic: so the snapshot shows exactly what the live app shows on the day it was
built. web/snapshot.js (loaded only in site/) replaces fetch("/api/...") with these files; a drawn box (or anything
not precomputed) gets a message that drawing needs the full app.
Open it with any static server: `python -m http.server -d site 8090`.
"""
from __future__ import annotations

import json
import shutil
import time
from pathlib import Path
from urllib.parse import urlencode

from godseye.config import Config

LANGS = ["en", "ar"]
UNITS = ["week", "day"]
METRICS = ["cell_days", "detections"]
SEASON = ["climatology", "critical-periods", "anomalies", "now"]


def js_number(x: float) -> str:
    """String(x) as JavaScript writes it for the coordinates the app sends (32.0 -> "32", 35.5 -> "35.5")."""
    return str(int(x)) if float(x).is_integer() else repr(float(x))


def file_for(endpoint: str, params: dict) -> str:
    """data/api/<endpoint>/<sorted query>.json; web/snapshot.js computes the same name from the request."""
    query = "&".join(f"{k}={params[k]}" for k in sorted(params)) or "index"
    return f"data/api/{endpoint}/{query}.json"


def build(cfg: Config, out: Path) -> dict:
    from fastapi.testclient import TestClient

    from godseye.api.app import app

    t0 = time.time()
    web = cfg.web_dir
    shutil.rmtree(out, ignore_errors=True)
    shutil.copytree(web, out, ignore=shutil.ignore_patterns("tools", "*.md"))
    saved, sizes = [], 0

    def save(client, endpoint: str, params: dict) -> dict:
        nonlocal sizes
        r = client.get(f"/api/{endpoint}" + (f"?{urlencode(params)}" if params else ""))
        body = {"status": r.status_code, "body": r.json()}       # errors (e.g. 409, 422) are kept as the app sees them
        path = out / file_for(endpoint, params)
        path.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps(body, ensure_ascii=False, separators=(",", ":"))
        path.write_text(text, encoding="utf-8")
        saved.append(path)
        sizes += len(text.encode("utf-8"))
        return body

    with TestClient(app) as client:
        for endpoint in ("health", "meta"):
            save(client, endpoint, {})
        aois = {}
        for lang in LANGS:
            aois[lang] = save(client, "aois", {"lang": lang})["body"]
        for a in aois["en"]:
            sensors, bbox = set(), None
            for lang in LANGS:
                for unit in UNITS:
                    for metric in METRICS:
                        cal = save(client, "calendar", {"aoi": a["name"], "lang": lang, "metric": metric,
                                                        "unit": unit})
                        if cal["status"] == 200:
                            sensors |= {s["sensor"] for s in cal["body"]["sensors"]}
                            bbox = cal["body"]["aoi"].get("grid_bbox") or cal["body"]["aoi"]["bbox"]
            for lang in LANGS:
                for series in ["harmonized", *sorted(sensors)]:
                    for ep in SEASON:
                        save(client, f"calendar/{ep}", {"aoi": a["name"], "lang": lang, "series": series})
            if bbox:
                save(client, "predictions/risk-map", {"bbox": ",".join(js_number(v) for v in bbox), "min_risk": "0"})

    built = time.strftime("%Y-%m-%d %H:%M")
    (out / ".nojekyll").write_text("")                 # GitHub Pages: serve every file as is
    (out / "data" / "snapshot.json").write_text(json.dumps({"built": built, "files": len(saved)}) + "\n")
    html = (out / "index.html").read_text(encoding="utf-8")
    shim = '  <script src="snapshot.js"></script>\n  <script src="app.js"></script>'
    assert html.count('  <script src="app.js"></script>') == 1
    (out / "index.html").write_text(html.replace('  <script src="app.js"></script>', shim), encoding="utf-8")
    return {"files": len(saved), "api_bytes": sizes, "built": built, "seconds": round(time.time() - t0, 1)}
