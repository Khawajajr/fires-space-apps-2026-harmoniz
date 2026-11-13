"""
HTTP API.

  GET /api/health
  GET /api/fires/recent            filtered recent detections as GeoJSON (default: last 24 h)
  GET /api/fires/recent.geojson    the full fires_recent.geojson file written by the pipeline
  GET /api/predictions/risk-map    7-day risk per grid cell from the trained model
  GET /api/predictions/risk-at     7-day risk at / around one point (agent and voice tools)
  GET /                            frontend/index.html (Leaflet dashboard)

`/api/fires/recent?format=firms` returns the record shape of NASA FIRMS area CSV rows
({lat, lon, frp, confidence, daynight, acqDate, acqTime, satellite, instrument}), which
the gods-eye-view 3D globe's Active Fires layer reads through its /api/gods-eye proxy.
"""
from __future__ import annotations

import time
from contextlib import asynccontextmanager

import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from godseye.clean.io import read_table as _read_table
from godseye.clean.schema import CONF_RANK
from godseye.config import get_config
from godseye.risk.model import load_bundle, predict_latest
from godseye.risk.panel import Panel, load_grid

CONFIG = get_config()
PROCESSED = CONFIG.processed_dir
MODEL_PATH = CONFIG.model_path
STATE: dict = {}


def read_table(stem: str) -> pd.DataFrame:
    return _read_table(PROCESSED, stem)


def load_predictions() -> tuple[pd.DataFrame, dict]:
    """Score the latest grid day with the trained model; fall back to the CSV written at training time."""
    if MODEL_PATH.exists():
        bundle = load_bundle(MODEL_PATH)
        preds = predict_latest(bundle, Panel(load_grid(), bundle["grid_deg"]))
        meta = {k: bundle[k] for k in ("grid_deg", "horizon_days", "risk_bins", "risk_labels",
                                       "trained_through", "validation")}
        return preds, meta
    fallback = CONFIG.predictions_path
    if fallback.exists():
        return pd.read_csv(fallback), {"grid_deg": CONFIG.risk["grid_deg"], "horizon_days": CONFIG.risk["horizon_days"],
                                       "source": fallback.name}
    raise FileNotFoundError("no model or risk predictions - run `godseye train`")


@asynccontextmanager
async def lifespan(app: FastAPI):
    t0 = time.time()
    fires = read_table("fires_recent")
    fires["acq_datetime"] = pd.to_datetime(fires["acq_datetime"], utc=True)
    fires["conf_rank"] = fires["confidence_class"].map(CONF_RANK).astype("int8")
    # FIRMS CSV spells the acquisition as date + unpadded-allowed HHMM; format once, not per request.
    fires["acq_date_str"] = fires["acq_datetime"].dt.strftime("%Y-%m-%d")
    fires["acq_hhmm"] = fires["acq_datetime"].dt.strftime("%H%M")
    STATE["fires"] = fires
    STATE["preds"], STATE["model_meta"] = load_predictions()
    print(f"loaded {len(fires):,} recent detections and {len(STATE['preds']):,} risk cells "
          f"in {time.time() - t0:.1f}s")
    yield
    STATE.clear()


app = FastAPI(title=f"{CONFIG.display_name} API", version="0.2.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET"], allow_headers=["*"])


def parse_bbox(bbox: str | None) -> tuple[float, float, float, float] | None:
    if not bbox:
        return None
    try:
        west, south, east, north = map(float, bbox.split(","))
    except ValueError:
        raise HTTPException(422, "bbox must be 'west,south,east,north' in degrees")
    return west, south, east, north


def in_bbox(lat: pd.Series, lon: pd.Series, bbox) -> pd.Series:
    west, south, east, north = bbox
    lon_ok = lon.between(west, east) if west <= east else (lon >= west) | (lon <= east)  # antimeridian
    return lat.between(south, north) & lon_ok


@app.get("/api/health")
def health():
    fires = STATE["fires"]
    return {"status": "ok", "recent_detections": len(fires),
            "recent_window": [fires.acq_datetime.min().isoformat(), fires.acq_datetime.max().isoformat()],
            "risk_cells": len(STATE["preds"]), "model": STATE["model_meta"]}


@app.get("/api/fires/recent")
def fires_recent(
    hours: int = Query(24, ge=1, le=24 * 7, description="look-back from the newest detection"),
    bbox: str | None = Query(None, description="west,south,east,north"),
    min_confidence: str = Query("nominal", pattern="^(low|nominal|high)$"),
    instrument: str | None = Query(None, pattern="^(MODIS|VIIRS)$"),
    limit: int = Query(50_000, ge=1, le=500_000),
    format: str = Query("geojson", pattern="^(geojson|firms)$"),
):
    df = STATE["fires"]
    m = (df.acq_datetime >= df.acq_datetime.max() - pd.Timedelta(hours=hours)) \
        & (df.conf_rank >= CONF_RANK[min_confidence])
    if instrument:
        m &= (df.sensor_res_m == 375) if instrument == "VIIRS" else (df.sensor_res_m == 1000)
    if (b := parse_bbox(bbox)) is not None:
        m &= in_bbox(df.latitude, df.longitude, b)
    sel = df[m]
    truncated = len(sel) > limit
    sel = sel.nlargest(limit, "frp_mw") if truncated else sel  # keep the most intense fires
    newest = df.acq_datetime.max()
    if format == "firms":
        fires = [
            {"lat": lat, "lon": lon, "frp": frp, "confidence": c, "daynight": dn, "acqDate": d,
             "acqTime": t, "satellite": s, "instrument": "VIIRS" if r == 375 else "MODIS"}
            for lat, lon, frp, c, dn, d, t, s, r in zip(
                sel.latitude.tolist(), sel.longitude.tolist(), sel.frp_mw.tolist(),
                sel.confidence_class.tolist(), sel.daynight.tolist(), sel.acq_date_str.tolist(),
                sel.acq_hhmm.tolist(), sel.satellite.tolist(), sel.sensor_res_m.tolist())
        ]
        # fetchedAt is the newest detection (data age), matching how the globe labels freshness.
        return JSONResponse({"fetchedAt": int(newest.timestamp() * 1000), "stale": False,
                             "sources": [{"source": "GODS_EYE_MODIS_VIIRS", "ok": True}],
                             "count": len(fires), "matched": int(m.sum()), "truncated": truncated,
                             "hours": hours, "fires": fires})
    times = sel.acq_datetime.dt.strftime("%Y-%m-%dT%H:%MZ").tolist()
    features = [
        {"type": "Feature", "geometry": {"type": "Point", "coordinates": [lon, lat]},
         "properties": {"t": t, "frp": frp, "conf": c, "sat": s, "res": r, "dn": dn}}
        for lon, lat, t, frp, c, s, r, dn in zip(
            sel.longitude.tolist(), sel.latitude.tolist(), times, sel.frp_mw.tolist(),
            sel.confidence_class.tolist(), sel.satellite.tolist(), sel.sensor_res_m.tolist(),
            sel.daynight.tolist())
    ]
    return JSONResponse({"type": "FeatureCollection", "features": features,
                         "metadata": {"count": len(features), "matched": int(m.sum()), "truncated": truncated,
                                      "hours": hours, "newest": newest.isoformat()}})


@app.get("/api/fires/recent.geojson")
def fires_recent_file():
    path = PROCESSED / "fires_recent.geojson"
    if not path.exists():
        raise HTTPException(404, "fires_recent.geojson not found - run `godseye clean`")
    return FileResponse(path, media_type="application/geo+json")


@app.get("/api/predictions/risk-map")
def risk_map(
    min_risk: float = Query(0.05, ge=0, le=1),
    bbox: str | None = Query(None, description="west,south,east,north"),
    format: str = Query("json", pattern="^(json|geojson)$"),
):
    df = STATE["preds"]
    m = df.risk >= min_risk
    if (b := parse_bbox(bbox)) is not None:
        m &= in_bbox(df.cell_lat, df.cell_lon, b)
    sel = df[m].sort_values("risk", ascending=False)
    meta = STATE["model_meta"]
    header = {"issued": str(df.issued.iat[0]), "valid_through": str(df.valid_through.iat[0]),
              "horizon_days": meta["horizon_days"], "cell_deg": meta["grid_deg"], "count": len(sel)}
    if format == "json":
        points = np.column_stack([sel.cell_lat, sel.cell_lon, sel.risk]).round(4).tolist()
        return JSONResponse({**header, "fields": ["lat", "lon", "risk"], "points": points,
                             "levels": sel.level.tolist()})
    h = meta["grid_deg"] / 2
    features = [
        {"type": "Feature", "properties": {"risk": r, "level": lv},
         "geometry": {"type": "Polygon", "coordinates": [[[lon - h, lat - h], [lon + h, lat - h],
                                                          [lon + h, lat + h], [lon - h, lat + h],
                                                          [lon - h, lat - h]]]}}
        for lat, lon, r, lv in zip(sel.cell_lat.tolist(), sel.cell_lon.tolist(), sel.risk.tolist(),
                                   sel.level.tolist())
    ]
    return JSONResponse({"type": "FeatureCollection", "features": features, "metadata": header})


def haversine_km(lat1, lon1, lat2, lon2):
    p1, p2 = np.radians(lat1), np.radians(lat2)
    a = np.sin((p2 - p1) / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(np.radians(lon2 - lon1) / 2) ** 2
    return 6371.0088 * 2 * np.arcsin(np.sqrt(a))


@app.get("/api/predictions/risk-at")
def risk_at(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    radius_km: float = Query(50, gt=0, le=1000),
    top: int = Query(5, ge=0, le=50),
):
    df = STATE["preds"]
    meta = STATE["model_meta"]
    dist = haversine_km(lat, lon, df.cell_lat.to_numpy(), df.cell_lon.to_numpy())
    nearest = int(np.argmin(dist))
    cell_half_diag_km = meta["grid_deg"] / 2 * 111.32 * np.sqrt(2)
    inside = dist <= radius_km
    sel = df[inside].assign(distance_km=dist[inside]).sort_values("risk", ascending=False)

    def cell(row):
        return {"lat": float(row.cell_lat), "lon": float(row.cell_lon), "risk": float(row.risk),
                "level": row.level, "distance_km": round(float(row.distance_km), 1)}

    near = df.iloc[nearest]
    covering = dist[nearest] <= cell_half_diag_km
    return {
        "issued": str(df.issued.iat[0]), "valid_through": str(df.valid_through.iat[0]),
        "horizon_days": meta["horizon_days"], "cell_deg": meta["grid_deg"],
        "query": {"lat": lat, "lon": lon, "radius_km": radius_km},
        # Only cells with fire activity since 2026-01-01 are scored; elsewhere the model has no basis.
        "point": ({"lat": float(near.cell_lat), "lon": float(near.cell_lon), "risk": float(near.risk),
                   "level": near.level, "scored": True} if covering else
                  {"scored": False, "risk": None, "level": "not_scored",
                   "note": "no satellite fire detections in this cell since 2026-01-01, so it is not "
                           "scored; such cells are historically very low risk"}),
        "area": {
            "scored_cells": int(len(sel)), "max_risk": float(sel.risk.max()) if len(sel) else None,
            "mean_risk": round(float(sel.risk.mean()), 4) if len(sel) else None,
            "level_counts": {k: int(v) for k, v in sel.level.value_counts().items()},
            "top": [cell(r) for r in sel.head(top).itertuples()],
        },
    }



# Mounted last so /api/* routes take precedence.
app.mount("/", StaticFiles(directory=CONFIG.frontend_dir, html=True), name="frontend")
