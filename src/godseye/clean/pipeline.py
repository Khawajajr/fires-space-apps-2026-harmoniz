"""
NASA FIRMS active-fire cleaning pipeline.

Reads any mix of FIRMS CSV downloads (MODIS C6.1 and/or VIIRS 375 m from
S-NPP / NOAA-20 / NOAA-21, archive "SP" and near-real-time "NRT"), maps them
onto one schema, filters invalid / non-wildfire detections, and writes:

  fires_clean.(feather|...)       one row per detection   -> model training / backend DB
  fires_daily_grid.(feather|...)  cell x day aggregates   -> spatial prediction labels
  fires_recent.(feather|...)      last N days, slim       -> API filtering source
  fires_recent.geojson            last N days, slim       -> web map layer

Files are streamed in chunks so the full multi-GB VIIRS archive fits in memory.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from godseye.clean.filters import global_filters, row_filters
from godseye.clean.io import iter_csvs, resolve_table_format, write_geojson, write_table
from godseye.clean.schema import CATEGORICAL, compact, harmonize_schema


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


def slim_recent(df: pd.DataFrame, days: int) -> pd.DataFrame:
    recent = df[df.acq_datetime >= df.acq_datetime.max() - pd.Timedelta(days=days)]
    return pd.DataFrame({
        "acq_datetime": recent.acq_datetime, "latitude": recent.latitude.round(5),
        "longitude": recent.longitude.round(5), "frp_mw": recent.frp_mw.astype("float64").round(1),
        "confidence_class": recent.confidence_class.astype(str), "satellite": recent.satellite.astype(str),
        "sensor_res_m": recent.sensor_res_m, "daynight": recent.daynight.astype(str),
    }).reset_index(drop=True)


def run(inputs: list[str], out_dir: Path, *, min_confidence: str = "nominal", grid_deg: float = 0.25,
        recent_days: int = 7, keep_static: bool = False, chunk_rows: int = 1_000_000,
        table_format: str = "feather") -> dict:
    """Clean FIRMS downloads into out_dir; returns the cleaning report."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    table_format = resolve_table_format(table_format)

    report, frames, per_file = {"input_rows": 0}, [], {}
    for name, raw in iter_csvs(inputs, chunk_rows):
        h = harmonize_schema(raw, name)
        report["input_rows"] += len(h)
        s = per_file.setdefault(name, {"rows": 0, "instrument": set(), "product": set(), "min": "9", "max": "0"})
        s["rows"] += len(h)
        s["instrument"].update(h.instrument.unique())
        s["product"].update(h["product"].unique())
        s["min"], s["max"] = min(s["min"], h.acq_date.min()), max(s["max"], h.acq_date.max())
        frames.append(compact(row_filters(h, min_confidence, report)))
    if not frames:
        raise SystemExit("no FIRMS CSVs found in inputs")
    for name, s in per_file.items():
        print(f"  read {name}: {s['rows']:,} rows  [{'/'.join(sorted(s['instrument']))} "
              f"{'/'.join(sorted(s['product']))} {s['min']} -> {s['max']}]")

    df = pd.concat(frames, ignore_index=True)  # concat unions categories across chunks
    del frames
    for c in CATEGORICAL:
        df[c] = df[c].astype("category")
    df = global_filters(df, keep_static, report)
    df = df.sort_values("acq_datetime", kind="stable").reset_index(drop=True)
    report["output_rows"] = len(df)
    report["output_by_instrument"] = {k: int(v) for k, v in df.instrument.value_counts().items()}
    report["output_by_satellite"] = {k: int(v) for k, v in df.satellite.value_counts().items()}
    for k, v in report.items():
        print(f"  {k:<42}{v:>12,}" if isinstance(v, int) else f"  {k:<42}{v}")

    p1 = write_table(df, out_dir / "fires_clean", table_format)
    p2 = write_table(daily_grid(df, grid_deg), out_dir / "fires_daily_grid", table_format)
    recent = slim_recent(df, recent_days)
    p3 = write_table(recent, out_dir / "fires_recent", table_format)
    p4 = out_dir / "fires_recent.geojson"
    write_geojson(recent, p4)
    (out_dir / "cleaning_report.json").write_text(json.dumps(report, indent=2))
    for p in (p1, p2, p3, p4):
        print(f"  wrote {p}  ({p.stat().st_size / 1e6:.1f} MB)")
    return report
