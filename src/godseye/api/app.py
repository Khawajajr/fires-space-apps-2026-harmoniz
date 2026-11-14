"""
HTTP API.

  GET /api/health
  GET /api/fires/recent            filtered recent detections as GeoJSON (default: last 24 h)
  GET /api/fires/recent.geojson    the full fires_recent.geojson file written by the pipeline
  GET /api/predictions/risk-map    7-day risk per grid cell from the trained model
  GET /api/predictions/risk-at     7-day risk at / around one point (agent and voice tools)
  GET /  (and /app/)               web/ calendar app (ADR 0003)
  GET /legacy/                     frontend/index.html (v0 Leaflet dashboard)

`/api/fires/recent?format=firms` returns the record shape of NASA FIRMS area CSV rows
({lat, lon, frp, confidence, daynight, acqDate, acqTime, satellite, instrument}), which
the gods-eye-view 3D globe's Active Fires layer reads through its /api/gods-eye proxy.
"""
from __future__ import annotations

import json
import logging
import time
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import asynccontextmanager

import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from godseye.api import calendar as calendar_api
from godseye.api import climatology as climatology_api
from godseye.calendar.harmonized import build_chain
from godseye.calendar.store import CalendarStore, in_bbox
from godseye.clean.io import find_table
from godseye.clean.io import read_table as _read_table
from godseye.clean.schema import CONF_RANK
from godseye.config import get_config
from godseye.harmonize import pipeline as harmonize_pipeline
from godseye.harmonize.link import display_method
from godseye.risk import artifact
from godseye.risk.model import predict_latest
from godseye.risk.panel import Panel, load_grid

CONFIG = get_config()
LOG = logging.getLogger("godseye.api")
PROCESSED = CONFIG.processed_dir
MODEL_DIR = CONFIG.model_dir
STATE: dict = {}


def read_table(stem: str) -> pd.DataFrame:
    return _read_table(PROCESSED, stem)


def load_predictions() -> tuple[pd.DataFrame, dict]:
    """Score the latest grid day with the trained model; fall back to the CSV written at training time."""
    if CONFIG.risk.get("serve") in ("v2", "v2.1") and not artifact.exists(CONFIG.served_model_dir):
        LOG.warning("risk.serve is %s but %s has no model; serving v1 (run `godseye train-v2`)", CONFIG.risk["serve"],
                    CONFIG.served_model_dir)
    if not artifact.exists(MODEL_DIR) and CONFIG.legacy_model_path.exists():
        artifact.migrate_pickle(CONFIG.legacy_model_path, MODEL_DIR, find_table(PROCESSED, "fires_daily_grid"),
                                CONFIG.root)
        LOG.warning("migrated %s to %s", CONFIG.legacy_model_path.name, MODEL_DIR)
    if CONFIG.risk.get("serve") in ("v2", "v2.1") and artifact.exists(CONFIG.served_model_dir):
        from godseye.risk import train_v2, v2
        from godseye.risk.model import risk_level

        bundle = artifact.load(CONFIG.served_model_dir)
        panel = train_v2.load_panel(CONFIG, PROCESSED, climatology=v2.CLIMATOLOGY_FEATURE in bundle["features"])
        preds = v2.predict_latest(bundle, panel, risk_level,
                                  issue=train_v2.last_full_day(CONFIG, PROCESSED))
        STATE["scored_by"] = CONFIG.risk_v2["reference_sensor"]
        meta = {k: bundle[k] for k in ("grid_deg", "horizon_days", "risk_bins", "risk_labels", "trained_through")}
        # Same keys as v1 in /api/health (contract): the held-out test scores when 11b has run, else validation.
        rows = bundle.get("test") or bundle["validation"]
        meta["validation"] = [{k: r[k] for k in ("model", "roc_auc", "pr_auc", "brier")} for r in rows]
        return preds, meta
    if artifact.exists(MODEL_DIR):
        bundle = artifact.load(MODEL_DIR)
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
    minutes = pd.Series(np.datetime_as_string(
        fires["acq_datetime"].dt.tz_convert(None).to_numpy().astype("datetime64[m]")))   # YYYY-MM-DDTHH:MM, UTC
    fires["acq_date_str"] = minutes.str[:10].to_numpy()
    fires["acq_hhmm"] = (minutes.str[11:13] + minutes.str[14:16]).to_numpy()
    STATE["fires"] = fires
    if (PROCESSED / "sensor_grid_daily.feather").exists():
        store = CalendarStore(read_table("sensor_grid_daily"), read_table("sensor_availability"),
                              CONFIG.clean["grid_deg"])
        if (PROCESSED / harmonize_pipeline.REPORT).exists():
            store.attach_chain(build_chain(CONFIG.harmonize["headline"], harmonize_pipeline.load(PROCESSED),
                                           CONFIG.harmonize["region_deg"]))
        calendar_api.STORE["calendar"] = store
        calendar_api.STORE["aoi"] = load_aoi_stores(store.chain)
        tiles = load_tiles(store.chain)
        if tiles is not None:
            calendar_api.STORE["tiles"] = tiles
    print(f"loaded {len(fires):,} recent detections and the calendar in {time.time() - t0:.1f}s; "
          "scoring risk in the background")
    # Scoring the latest day takes ~3-8 s. A forecast cached for the same model and data loads at once (the first
    # risk call is then instant); otherwise it is scored off the startup path and cached. Risk endpoints wait for it
    # (see risk_state), so their responses are unchanged.
    executor = ThreadPoolExecutor(max_workers=1)
    STATE["executor"] = executor
    hit = cached_predictions()
    if hit is not None:
        STATE["risk"] = Future()
        STATE["risk"].set_result(hit)
        LOG.warning("risk forecast loaded from cache (issued %s)", hit[0].issued.iloc[0] if len(hit[0]) else "-")
    else:
        STATE["risk"] = executor.submit(score_and_cache)
    yield
    executor.shutdown(wait=True)
    STATE.clear()
    calendar_api.STORE.clear()


def load_aoi_stores(chain) -> dict:
    """Multi-year stores built by `godseye ingest --aoi` (data/processed/aoi/<name>/), keyed by AOI name."""
    out = {}
    for d in sorted((PROCESSED / "aoi").glob("*/")):
        if d.name in CONFIG.aois and (d / "sensor_grid_daily.feather").exists():
            s = CalendarStore(_read_table(d, "sensor_grid_daily"), _read_table(d, "sensor_availability"),
                              CONFIG.clean["grid_deg"])
            s.attach_chain(chain)
            out[d.name] = (CONFIG.aois[d.name].bbox, s)
            LOG.warning("multi-year calendar for %s: %s to %s", d.name, s.first.date(), s.last.date())
    return out


def load_tiles(chain):
    """The global multi-year 0.25° tiles from `godseye ingest-archive`, loaded lazily per requested box."""
    from godseye.calendar.tiles import TileStores

    d = PROCESSED / "archive"
    if not (d / "tiles").is_dir() or not (d / "sensor_availability.feather").exists():
        return None
    t = TileStores(d / "tiles", _read_table(d, "sensor_availability"), CONFIG.clean["grid_deg"], chain,
                   CONFIG.api.get("tile_cache", 8), int(CONFIG.api.get("tile_max_rows", 30_000_000)))
    LOG.warning("global multi-year tiles: %d files, %s to %s", len(t.available), t.first.date(), t.last.date())
    return t


RISK_CACHE = "risk_forecast_cache"


def risk_cache_key() -> dict:
    """What the served forecast depends on: the model files and the data it is scored from (size + mtime)."""
    files = [CONFIG.served_model_dir / artifact.MODEL, CONFIG.served_model_dir / artifact.META,
             PROCESSED / "sensor_grid_daily.feather", PROCESSED / "sensor_availability.feather",
             PROCESSED / "archive" / "n20_week_climatology.feather", MODEL_DIR / artifact.MODEL]
    stat = lambda p: [p.stat().st_size, p.stat().st_mtime_ns] if p.exists() else None
    return {"serve": CONFIG.risk.get("serve"), "files": {p.as_posix(): stat(p) for p in files}}


def cached_predictions() -> tuple[pd.DataFrame, dict] | None:
    try:
        info = json.loads((PROCESSED / f"{RISK_CACHE}.json").read_text())
        if info["key"] != risk_cache_key():
            return None
        if info.get("scored_by"):
            STATE["scored_by"] = info["scored_by"]
        return pd.read_feather(PROCESSED / f"{RISK_CACHE}.feather"), info["meta"]
    except (OSError, ValueError, KeyError):
        return None


def score_and_cache() -> tuple[pd.DataFrame, dict]:
    preds, meta = load_predictions()
    try:
        preds.reset_index(drop=True).to_feather(PROCESSED / f"{RISK_CACHE}.feather")
        (PROCESSED / f"{RISK_CACHE}.json").write_text(json.dumps(
            {"key": risk_cache_key(), "meta": meta, "scored_by": STATE.get("scored_by")}, default=str))
    except Exception as e:  # noqa: BLE001 - a failed cache write (read-only folder, ...) must not stop serving
        LOG.warning("could not cache the risk forecast: %s", e)
    return preds, meta


def risk_state() -> tuple[pd.DataFrame, dict]:
    """(predictions, model metadata), waiting for the background scoring the first time.

    If scoring failed, log it, answer 503 and start it again so a later request can succeed."""
    future = STATE["risk"]
    try:
        return future.result()
    except Exception as err:   # noqa: BLE001 - any scoring failure must not take the API down for good
        LOG.exception("risk scoring failed: %s", err)
        if STATE["risk"] is future:
            STATE["risk"] = STATE["executor"].submit(score_and_cache)
        raise HTTPException(503, "risk forecast unavailable; retrying") from err


app = FastAPI(title=f"{CONFIG.display_name} API", version="0.2.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET"], allow_headers=["*"])
app.include_router(calendar_api.router)
app.include_router(climatology_api.router)


def parse_bbox(bbox: str | None) -> tuple[float, float, float, float] | None:
    if not bbox:
        return None
    try:
        west, south, east, north = map(float, bbox.split(","))
    except ValueError:
        raise HTTPException(422, "bbox must be 'west,south,east,north' in degrees")
    return west, south, east, north


@app.get("/api/health")
def health():
    fires = STATE["fires"]
    preds, meta = risk_state()
    return {"status": "ok", "recent_detections": len(fires),
            "recent_window": [fires.acq_datetime.min().isoformat(), fires.acq_datetime.max().isoformat()],
            "risk_cells": len(preds), "model": meta}


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
    df, meta = risk_state()
    m = df.risk >= min_risk
    if (b := parse_bbox(bbox)) is not None:
        m &= in_bbox(df.cell_lat, df.cell_lon, b)
    sel = df[m].sort_values("risk", ascending=False)
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
    df, meta = risk_state()
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
                   "note": f"no {STATE.get('scored_by', 'satellite')} fire detections in this cell since the data "
                           "starts, so it is not scored; such cells are historically very low risk"}),
        "area": {
            "scored_cells": int(len(sel)), "max_risk": float(sel.risk.max()) if len(sel) else None,
            "mean_risk": round(float(sel.risk.mean()), 4) if len(sel) else None,
            "level_counts": {k: int(v) for k, v in sel.level.value_counts().items()},
            "top": [cell(r) for r in sel.head(top).itertuples()],
        },
    }



class SensorCoverage(BaseModel):
    sensor: str
    first_day: str | None
    last_day: str | None
    days: dict[str, int] = Field(description="days per availability status in the data range")


class StoreRange(BaseModel):
    name: str = Field(description="'global' or the named AOI whose multi-year store serves requests inside it")
    kind: str = Field(description="global | aoi | tiles (global multi-year, loaded per requested box)")
    bbox: list[float] | None
    first_day: str
    last_day: str
    years: int


class MetaResponse(BaseModel):
    name: str
    api_version: str
    challenge: str
    data_range: list[str] | None = Field(description="first and last day over all calendar stores")
    stores: list[StoreRange] = Field(default_factory=list, description="date range of each calendar store")
    sensors: list[SensorCoverage] = Field(description="per-sensor coverage of the global store")
    model: dict | None = Field(description="risk model artifact: name, version, created_at, git_sha, data_sha256, ...")
    harmonization: list[dict] = Field(description="sensor links: source, target, method, provisional")
    aois: list[str]
    attribution: list[str]


MODEL_INFO_FIELDS = ("name", "version", "created_at", "trained_through", "git_sha", "data_sha256", "num_trees",
                     "label", "blocks", "test_scored", "migrated_from", "migrated_at", "note")


def model_info() -> dict | None:
    """From the committed metadata file, so it never waits for (or races with) the background scoring."""
    meta = artifact.read_meta(CONFIG.served_model_dir)
    return None if meta is None else {k: meta.get(k) for k in MODEL_INFO_FIELDS}


ATTRIBUTION = [
    "Fire data: NASA FIRMS (MODIS C6.1 MCD14ML; VIIRS 375 m C2 VNP14IMG, VJ114IMG, VJ214IMG). We acknowledge the use "
    "of data and/or imagery from NASA's Fire Information for Resource Management System (FIRMS), part of NASA's Earth "
    "Science Data and Information System (ESDIS).",
    "Boundaries: Made with Natural Earth (public domain).",
    "Map: Leaflet (BSD-2-Clause). Globe: gods-eye-view by Bilawal Sidhu (MIT).",
    "Full list: docs/REFERENCES.md.",
]


def store_range(name: str, kind: str, bbox: list[float] | None, store) -> StoreRange:
    return StoreRange(name=name, kind=kind, bbox=bbox, first_day=store.first.strftime("%Y-%m-%d"),
                      last_day=store.last.strftime("%Y-%m-%d"), years=store.last.year - store.first.year + 1)


@app.get("/api/meta", response_model=MetaResponse)
def meta():
    store = calendar_api.STORE.get("calendar")
    sensors, data_range = [], None
    if store is not None:
        data_range = [store.first.strftime("%Y-%m-%d"), store.last.strftime("%Y-%m-%d")]
        names = {0: "ok", 1: "partial", 2: "gap"}
        for i, name in enumerate(store.sensors):
            st = store.status[i]
            has = np.flatnonzero(st != 2)
            sensors.append(SensorCoverage(
                sensor=name,
                first_day=str(store.dates[has[0]].date()) if len(has) else None,
                last_day=str(store.dates[has[-1]].date()) if len(has) else None,
                days={names[k]: int((st == k).sum()) for k in names}))
    stores = [store_range("global", "global", None, store)] if store is not None else []
    stores += [store_range(name, "aoi", list(bbox), s) for name, (bbox, s) in calendar_api.STORE.get("aoi", {}).items()]
    if "tiles" in calendar_api.STORE:                      # any other box: the global multi-year tiles
        stores.append(store_range("global_tiles", "tiles", None, calendar_api.STORE["tiles"]))
    if stores:
        data_range = [min(s.first_day for s in stores), max(s.last_day for s in stores)]
    links = []
    if store is not None and store.chain is not None:
        chain = store.chain
        for k in [c for c in chain.continuity.values() if c is not None] + [chain.headline]:
            links.append({"source": k.source, "target": k.target, "method": display_method(k),
                          "provisional": k.provisional})
    return MetaResponse(name=CONFIG.display_name, api_version=app.version,
                        challenge="NASA Space Apps 2026: Harmonization of MODIS and VIIRS Hot Spots",
                        data_range=data_range, stores=stores, sensors=sensors, model=model_info(),
                        harmonization=links, aois=sorted(CONFIG.aois), attribution=ATTRIBUTION)


# Mounted last so /api/* routes take precedence.
app.mount("/app", StaticFiles(directory=CONFIG.web_dir, html=True), name="web")  # ADR 0003: primary product
app.mount("/legacy", StaticFiles(directory=CONFIG.frontend_dir, html=True), name="frontend")  # v0 Leaflet dashboard
app.mount("/", StaticFiles(directory=CONFIG.web_dir, html=True), name="home")  # the calendar app is the default page
