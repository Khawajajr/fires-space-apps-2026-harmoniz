"""
God's Eye - NASA FIRMS active-fire cleaning & harmonization pipeline.

Reads any mix of FIRMS CSV downloads (MODIS C6.1 and/or VIIRS 375 m from
S-NPP / NOAA-20 / NOAA-21, archive "SP" and near-real-time "NRT"), maps them
onto one schema, filters invalid / non-wildfire detections, and writes:

  fires_clean.(parquet|feather|csv.gz)       one row per detection   -> model training / backend DB
  fires_daily_grid.(parquet|feather|csv.gz)  cell x day aggregates   -> spatial prediction labels
  fires_recent.(parquet|feather|csv.gz)      last N days, slim       -> API filtering source
  fires_recent.geojson               last N days, slim       -> web map layer

Files are streamed in chunks so the full multi-GB VIIRS archive fits in memory.

Usage:
  python clean_fire_data.py <csv|zip|dir> [...] --out ../data/processed
         [--min-confidence nominal] [--grid-deg 0.25] [--recent-days 7] [--keep-static]
"""
from __future__ import annotations

import argparse
import importlib
import json
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

def _importable(module: str) -> bool:
    # Actually import: on Smart App Control machines pyarrow is installed but its _parquet DLL is blocked.
    try:
        importlib.import_module(module)
        return True
    except ImportError:
        return False


TABLE_FORMAT = ("parquet" if _importable("pyarrow.parquet")
                else "feather" if _importable("pyarrow.feather") else "csv")
CHUNK_ROWS = 1_000_000

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


def iter_csvs(paths: list[str]):
    """Yield (name, chunk) for every CSV chunk in the given files/dirs/zips."""
    read = lambda src: pd.read_csv(src, dtype=str, chunksize=CHUNK_ROWS)
    for p in map(Path, paths):
        if p.is_dir():
            yield from iter_csvs([str(x) for x in sorted(p.rglob("*")) if x.suffix.lower() in (".csv", ".zip")])
        elif p.suffix.lower() == ".zip":
            with zipfile.ZipFile(p) as zf:
                for n in zf.namelist():
                    if n.lower().endswith(".csv"):
                        with zf.open(n) as fh:
                            for chunk in read(fh):
                                yield f"{p.name}!{n}", chunk
        elif p.suffix.lower() == ".csv":
            for chunk in read(p):
                yield p.name, chunk


def harmonize(raw: pd.DataFrame, source: str) -> pd.DataFrame:
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


def row_filters(df: pd.DataFrame, min_conf: str, report: dict) -> pd.DataFrame:
    """Per-row checks that need no global context; applied chunk by chunk."""
    def drop(mask, reason):
        nonlocal df
        report[reason] = report.get(reason, 0) + int(mask.sum())
        df = df[~mask]

    drop(df[["latitude", "longitude", "acq_datetime", "frp_mw", "confidence_class"]].isna().any(axis=1),
         "dropped_missing_core_fields")
    drop(~df.latitude.between(-90, 90) | ~df.longitude.between(-180, 180), "dropped_bad_coords")
    drop(df.frp_mw <= 0, "dropped_frp_le_zero")
    drop(df.confidence_class.map(CONF_RANK) < CONF_RANK[min_conf], f"dropped_confidence_below_{min_conf}")
    return df


def compact(df: pd.DataFrame) -> pd.DataFrame:
    for c in ["pixel_area_km2", "brightness_k", "bright_t31_k", "frp_mw", "confidence_pct"]:
        df[c] = df[c].astype("float32")
    for c in CATEGORICAL:
        df[c] = df[c].astype("category")
    return df


def cell_key(lat: pd.Series, lon: pd.Series, deg: float) -> np.ndarray:
    return (np.floor(lat.to_numpy() / deg).astype(np.int64) * 100_000
            + np.floor(lon.to_numpy() / deg).astype(np.int64))


def static_source_mask(df: pd.DataFrame, cell_deg: float = 0.02) -> np.ndarray:
    """
    NRT files have no `type` column. Flag NRT detections that fall in ~2 km cells
    where the archive has labelled volcanoes / static industrial sources (type 1-2),
    so gas flares and steel plants do not leak into wildfire training data.
    Heuristic: it only knows sources seen in the archive period.
    """
    static = df["type"].isin([1, 2]).to_numpy()
    if not static.any():
        return np.zeros(len(df), dtype=bool)
    keys = cell_key(df.latitude, df.longitude, cell_deg)
    return df["type"].isna().to_numpy() & np.isin(keys, np.unique(keys[static]))


def global_filters(df: pd.DataFrame, keep_static: bool, report: dict) -> pd.DataFrame:
    def drop(mask, reason):
        nonlocal df
        mask = np.asarray(mask, dtype=bool)
        report[reason] = int(mask.sum())
        df = df[~mask]

    if not keep_static:
        near_static = static_source_mask(df)  # must run while archive type 1-2 rows still exist
        non_veg = (df["type"].notna() & (df["type"] != WILDFIRE_TYPE)).to_numpy(dtype=bool, na_value=False)
        report["dropped_non_vegetation_type"] = int(non_veg.sum())
        report["dropped_nrt_near_known_static_source"] = int(near_static.sum())
        df = df[~(non_veg | near_static)]

    # When archive and NRT overlap for a satellite-day, the archive (standard, reprocessed) wins.
    day_key = df.satellite.cat.codes.to_numpy().astype(np.int64) * 100_000 + df.acq_date.cat.codes.to_numpy()
    is_nrt = (df["product"] == "nrt").to_numpy()
    drop(is_nrt & np.isin(day_key, np.unique(day_key[~is_nrt])), "dropped_nrt_superseded_by_archive")

    drop(df.duplicated(["satellite", "acq_datetime", "latitude", "longitude"]), "dropped_duplicates")
    return df


def daily_grid(df: pd.DataFrame, deg: float) -> pd.DataFrame:
    """Aggregate detections to (cell, day): the label table for a spatial fire-occurrence model."""
    g = pd.DataFrame({
        "acq_date": df.acq_date.astype(str).to_numpy(),
        "cell_lat": (np.floor(df.latitude.to_numpy() / deg) * deg + deg / 2).round(4),
        "cell_lon": (np.floor(df.longitude.to_numpy() / deg) * deg + deg / 2).round(4),
        "frp_mw": df.frp_mw.to_numpy(),
        "is_high": (df.confidence_class == "high").to_numpy(np.int32),
        "is_night": (df.daynight == "N").to_numpy(np.int32),
        "is_viirs": (df.instrument == "VIIRS").to_numpy(np.int32),
        "bt31": df.bright_t31_k.to_numpy(),
    })
    out = (g.groupby(["acq_date", "cell_lat", "cell_lon"], sort=True)
            .agg(n_detections=("frp_mw", "size"), frp_sum_mw=("frp_mw", "sum"),
                 frp_max_mw=("frp_mw", "max"), n_high_conf=("is_high", "sum"),
                 n_night=("is_night", "sum"), n_viirs=("is_viirs", "sum"),
                 bt31_mean_k=("bt31", "mean"))
            .reset_index())
    out["n_modis"] = out.n_detections - out.n_viirs
    return out


def write_table(df: pd.DataFrame, path_stem: Path) -> Path:
    if TABLE_FORMAT == "parquet":
        path = path_stem.with_suffix(".parquet")
        df.to_parquet(path, index=False)
    elif TABLE_FORMAT == "feather":
        path = path_stem.with_suffix(".feather")
        df.reset_index(drop=True).to_feather(path, compression="zstd")
    else:
        path = path_stem.with_suffix(".csv.gz")
        out = df.copy()
        if "acq_datetime" in out:
            out["acq_datetime"] = out["acq_datetime"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        out.to_csv(path, index=False, compression="gzip")
    return path


def slim_recent(df: pd.DataFrame, days: int) -> pd.DataFrame:
    recent = df[df.acq_datetime >= df.acq_datetime.max() - pd.Timedelta(days=days)]
    return pd.DataFrame({
        "acq_datetime": recent.acq_datetime, "latitude": recent.latitude.round(5),
        "longitude": recent.longitude.round(5), "frp_mw": recent.frp_mw.astype("float64").round(1),
        "confidence_class": recent.confidence_class.astype(str), "satellite": recent.satellite.astype(str),
        "sensor_res_m": recent.sensor_res_m, "daynight": recent.daynight.astype(str),
    }).reset_index(drop=True)


def write_geojson(recent: pd.DataFrame, path: Path) -> None:
    """Slim point FeatureCollection; 5-decimal coords (~1 m) keep the file small for the browser."""
    feats = [
        {"type": "Feature",
         "geometry": {"type": "Point", "coordinates": [lon, lat]},
         "properties": {"t": t, "frp": frp, "conf": c, "sat": s, "res": int(r), "dn": dn}}
        for lon, lat, t, frp, c, s, r, dn in zip(
            recent.longitude, recent.latitude, recent.acq_datetime.dt.strftime("%Y-%m-%dT%H:%MZ"),
            recent.frp_mw.astype(float), recent.confidence_class, recent.satellite,
            recent.sensor_res_m, recent.daynight)
    ]
    path.write_text(json.dumps({"type": "FeatureCollection", "features": feats}, separators=(",", ":")))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("inputs", nargs="+", help="FIRMS CSV files, zips, or directories")
    ap.add_argument("--out", default=str(Path(__file__).resolve().parent.parent / "data" / "processed"))
    ap.add_argument("--min-confidence", choices=list(CONF_RANK), default="nominal")
    ap.add_argument("--grid-deg", type=float, default=0.25)
    ap.add_argument("--recent-days", type=int, default=7)
    ap.add_argument("--keep-static", action="store_true", help="keep volcano/industrial/offshore detections")
    args = ap.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    report, frames, per_file = {"input_rows": 0}, [], {}
    for name, raw in iter_csvs(args.inputs):
        h = harmonize(raw, name)
        report["input_rows"] += len(h)
        s = per_file.setdefault(name, {"rows": 0, "instrument": set(), "product": set(), "min": "9", "max": "0"})
        s["rows"] += len(h)
        s["instrument"].update(h.instrument.unique())
        s["product"].update(h["product"].unique())
        s["min"], s["max"] = min(s["min"], h.acq_date.min()), max(s["max"], h.acq_date.max())
        frames.append(compact(row_filters(h, args.min_confidence, report)))
    if not frames:
        raise SystemExit("no FIRMS CSVs found in inputs")
    for name, s in per_file.items():
        print(f"  read {name}: {s['rows']:,} rows  [{'/'.join(sorted(s['instrument']))} "
              f"{'/'.join(sorted(s['product']))} {s['min']} -> {s['max']}]")

    df = pd.concat(frames, ignore_index=True)  # concat unions categories across chunks
    del frames
    for c in CATEGORICAL:
        df[c] = df[c].astype("category")
    df = global_filters(df, args.keep_static, report)
    df = df.sort_values("acq_datetime", kind="stable").reset_index(drop=True)
    report["output_rows"] = len(df)
    report["output_by_instrument"] = {k: int(v) for k, v in df.instrument.value_counts().items()}
    report["output_by_satellite"] = {k: int(v) for k, v in df.satellite.value_counts().items()}
    for k, v in report.items():
        print(f"  {k:<42}{v:>12,}" if isinstance(v, int) else f"  {k:<42}{v}")

    p1 = write_table(df, out_dir / "fires_clean")
    p2 = write_table(daily_grid(df, args.grid_deg), out_dir / "fires_daily_grid")
    recent = slim_recent(df, args.recent_days)
    p3 = write_table(recent, out_dir / "fires_recent")
    p4 = out_dir / "fires_recent.geojson"
    write_geojson(recent, p4)
    (out_dir / "cleaning_report.json").write_text(json.dumps(report, indent=2))
    for p in (p1, p2, p3, p4):
        print(f"  wrote {p}  ({p.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
