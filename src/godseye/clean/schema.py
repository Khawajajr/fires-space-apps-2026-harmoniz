"""Seam 1: raw FIRMS rows (MODIS C6.1, VIIRS 375 m; archive or NRT; CSV/API spellings) -> one unified schema."""
from __future__ import annotations

import numpy as np
import pandas as pd

# FIRMS satellite codes -> canonical names (CSV, SHP and API spellings differ).
SATELLITE_MAP = {
    "Terra": "Terra", "T": "Terra",
    "Aqua": "Aqua", "A": "Aqua",
    "N": "Suomi-NPP", "NPP": "Suomi-NPP", "SNPP": "Suomi-NPP", "Suomi NPP": "Suomi-NPP",
    "1": "NOAA-20", "N20": "NOAA-20", "J1": "NOAA-20", "NOAA-20": "NOAA-20",
    "2": "NOAA-21", "N21": "NOAA-21", "J2": "NOAA-21", "NOAA-21": "NOAA-21",
}
VIIRS_SATELLITES = {"Suomi-NPP", "NOAA-20", "NOAA-21"}
VIIRS_CONF_MAP = {"l": "low", "low": "low", "n": "nominal", "nominal": "nominal",
                  "h": "high", "high": "high"}
CONF_RANK = {"low": 0, "nominal": 1, "high": 2}
# Archive "type": 0 vegetation fire, 1 active volcano, 2 other static land source, 3 offshore.
WILDFIRE_TYPE = 0
UNIFIED_COLUMNS = [
    "acq_datetime", "acq_date", "latitude", "longitude", "satellite", "instrument",
    "sensor_res_m", "pixel_area_km2", "brightness_k", "bright_t31_k", "frp_mw",
    "confidence_class", "confidence_pct", "daynight", "type", "product", "version", "source_file",
]
CATEGORICAL = ["acq_date", "satellite", "instrument", "confidence_class", "daynight", "product",
               "version", "source_file"]


def harmonize_schema(raw: pd.DataFrame, source: str) -> pd.DataFrame:
    """Map one raw FIRMS table (all-string dtypes) onto UNIFIED_COLUMNS."""
    cols = set(raw.columns)
    num = lambda c: pd.to_numeric(raw[c], errors="coerce") if c in cols else np.nan

    out = pd.DataFrame(index=raw.index)
    out["latitude"] = num("latitude")
    out["longitude"] = num("longitude")

    # acq_date (YYYY-MM-DD) + acq_time (HHMM, UTC, leading zeros sometimes dropped) -> tz-aware UTC
    hhmm = raw["acq_time"].str.strip().str.zfill(4)
    out["acq_datetime"] = pd.to_datetime(raw["acq_date"].str.strip() + " " + hhmm,
                                         format="%Y-%m-%d %H%M", utc=True, errors="coerce")
    out["acq_date"] = out["acq_datetime"].dt.strftime("%Y-%m-%d")

    sat = raw["satellite"].str.strip()
    out["satellite"] = sat.map(SATELLITE_MAP).fillna(sat)
    # VIIRS CSVs from FIRMS reuse MODIS column names (brightness / bright_t31 hold I4 / I5),
    # and S-NPP files say "SNPP" in the instrument field, so decide from the satellite.
    # Older/API exports use bright_ti4 / bright_ti5 instead.
    is_viirs = out["satellite"].isin(VIIRS_SATELLITES)
    out["instrument"] = np.where(is_viirs, "VIIRS", "MODIS")
    out["sensor_res_m"] = np.where(is_viirs, 375, 1000).astype("int16")
    # scan/track are the actual off-nadir pixel dimensions in km (MODIS grows to ~4.8 x 2 km).
    out["pixel_area_km2"] = num("scan") * num("track")

    out["brightness_k"] = num("bright_ti4" if "bright_ti4" in cols else "brightness")
    out["bright_t31_k"] = num("bright_ti5" if "bright_ti5" in cols else "bright_t31")
    out["frp_mw"] = num("frp")

    conf = raw["confidence"].str.strip()
    pct = pd.to_numeric(conf, errors="coerce").where(~is_viirs)  # VIIRS has no numeric confidence
    out["confidence_pct"] = pct
    # MODIS thresholds from the C6.1 user guide: <30 low, 30-79 nominal, >=80 high.
    modis_class = pd.cut(pct, [-1, 29, 79, 100], labels=["low", "nominal", "high"]).astype(object)
    out["confidence_class"] = np.where(is_viirs, conf.str.lower().map(VIIRS_CONF_MAP), modis_class)
    out.loc[out["confidence_class"].isna() | (out["confidence_class"] == "nan"), "confidence_class"] = None

    out["daynight"] = raw.get("daynight")
    out["type"] = pd.to_numeric(raw["type"], errors="coerce").astype("Int8") if "type" in cols else pd.array(
        [pd.NA] * len(raw), dtype="Int8")
    version = raw["version"].astype(str)
    out["version"] = version
    out["product"] = np.where(version.str.contains("NRT", case=False), "nrt", "archive")
    out["source_file"] = source
    return out[UNIFIED_COLUMNS]


def compact(df: pd.DataFrame) -> pd.DataFrame:
    for c in ["pixel_area_km2", "brightness_k", "bright_t31_k", "frp_mw", "confidence_pct"]:
        df[c] = df[c].astype("float32")
    for c in CATEGORICAL:
        df[c] = df[c].astype("category")
    return df
