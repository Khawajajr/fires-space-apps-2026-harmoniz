"""
`godseye ingest-archive` (ticket 07, rescoped): the global FIRMS archive zips (one sensor-year each), read in place.

One streaming pass per zip reuses seam 1 (harmonize_schema, row_filters, global_filters) and the per-sensor fire-cell
aggregation, and writes small partial tables under data/processed/archive/parts/<sha256>/:

  daily      sensor x day global detections            -> availability 2012-2025 (gaps stay "no data", never 0)
  region     sensor x day x 10° block fire cell-days   -> global calibration of the sensor links (ticket 08)
  aoi_<name> sensor x day x 0.01° fire cells in an AOI  -> multi-year AOI stores (Levant, Argentina)
  n20_weeks  NOAA-20 0.25° cell x year x week with >= 1 fire cell-day -> weekly climatology for the risk baseline
  g025/      sensor x day x 0.25° cell, split into 10° tiles -> the global multi-year calendar for any drawn box

Zips run in parallel (one process each). A zip whose sha256 already has a finished part is skipped, so a crash
resumes where it stopped. The merge step adds 2026 from the processed global tables (data/raw itself is not reread)
and asserts the archives never overlap data/raw by date.
"""
from __future__ import annotations

import json
import os
import shutil
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd

from godseye.clean.filters import global_filters, row_filters
from godseye.clean.io import iter_csvs, read_table
from godseye.clean.pipeline import inside_bbox
from godseye.clean.schema import compact, harmonize_schema
from godseye.config import Config
from godseye.ingest.aggregate import availability, fire_cells, sensor_grid
from godseye.ingest.manifest import FIRMS_DOWNLOAD_URL, sha256

USECOLS = ["latitude", "longitude", "acq_date", "acq_time", "satellite", "confidence", "version", "frp", "daynight",
           "type"]
CELL_KEYS = ["sensor", "acq_date", "lat_i", "lon_i"]
CLIMATOLOGY_YEARS = (2019, 2025)
PART_VERSION = 2          # 2: + g025 tiles. Parts written by an older version are read again.
TILE_DEG = 10


def tile_name(lat: np.ndarray, lon: np.ndarray, deg: float = TILE_DEG) -> np.ndarray:
    """'t_+30_+030' style tile id (south-west corner) of each 0.25° cell centre."""
    la = (np.floor(np.asarray(lat) / deg) * deg).astype(int)
    lo = (np.floor(np.asarray(lon) / deg) * deg).astype(int)
    return np.char.add(np.char.add(np.char.add("t_", np.char.mod("%+03d", la)), "_"), np.char.mod("%+04d", lo))


def write_tiles(grid: pd.DataFrame, folder: Path) -> int:
    folder.mkdir(parents=True, exist_ok=True)
    names = tile_name(grid.cell_lat.to_numpy(), grid.cell_lon.to_numpy())
    for name, idx in pd.Series(np.arange(len(grid))).groupby(names):
        grid.iloc[idx.to_numpy()].reset_index(drop=True).to_feather(folder / f"{name}.feather")
    return len(set(names))


def week_of_year(dates: pd.Series) -> np.ndarray:
    """0-51: seven-day blocks from 1 January, the last block taking the 1-2 spare days (same rule as the risk model)."""
    return np.minimum((dates.dt.dayofyear.to_numpy() - 1) // 7, 51)


def cell_centres(cells: pd.DataFrame, fine: float) -> tuple[pd.Series, pd.Series]:
    return (cells.lat_i + 0.5) * fine, (cells.lon_i + 0.5) * fine


def process_zip(path: str, out_root: str, sha: str, sensors: dict, aois: dict, fine: float, coarse: float,
                region_deg: float, min_conf: str, chunk_rows: int) -> dict:
    """One zip -> partial tables in out_root/<sha>/ (written to a temp folder, renamed when complete)."""
    t0 = time.time()
    tmp, final = Path(out_root) / f"{sha}.tmp", Path(out_root) / sha
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    rows, first, last, sats, versions, report, parts = 0, None, None, Counter(), Counter(), Counter(), []
    for name, raw in iter_csvs([path], chunk_rows, usecols=USECOLS):
        rows += len(raw)
        lo, hi = raw.acq_date.min(), raw.acq_date.max()
        first = lo if first is None or lo < first else first
        last = hi if last is None or hi > last else last
        sats.update(raw.satellite.value_counts().to_dict())
        versions.update(raw.version.value_counts().to_dict())
        chunk_report: dict = {}
        det = compact(row_filters(harmonize_schema(raw, name), min_conf, chunk_report))
        det = global_filters(det, False, chunk_report)
        report.update(chunk_report)
        report["detections_kept"] += len(det)
        parts.append(fire_cells(det, sensors, fine))
    cells = (pd.concat(parts, ignore_index=True)
             .groupby(CELL_KEYS, observed=True, sort=True)[["n_detections", "n_detections_daytime", "frp_sum_mw"]]
             .sum().reset_index())          # a cell-day split across two chunks is merged here
    cells["sensor"] = pd.Categorical(cells.sensor.astype(str), categories=list(sensors))
    cells.groupby(["sensor", "acq_date"], observed=True).n_detections.sum().reset_index() \
        .to_feather(tmp / "daily.feather")
    sensor_grid(cells, fine, region_deg).to_feather(tmp / "region.feather")
    write_tiles(sensor_grid(cells, fine, coarse), tmp / "g025")
    lat, lon = cell_centres(cells, fine)
    for aoi, bbox in aois.items():
        cells[inside_bbox(lat, lon, bbox).to_numpy()].reset_index(drop=True).to_feather(tmp / f"aoi_{aoi}.feather")
    n20 = cells[cells.sensor.astype(str) == "NOAA-20-VIIRS"]
    if len(n20):
        g = sensor_grid(n20, fine, coarse)
        d = pd.to_datetime(g.acq_date)
        pd.DataFrame({"cell_lat": g.cell_lat, "cell_lon": g.cell_lon, "year": d.dt.year.astype(np.int16),
                      "week": week_of_year(d).astype(np.int8)}).drop_duplicates().reset_index(drop=True) \
            .to_feather(tmp / "n20_weeks.feather")
    meta = {"version": PART_VERSION, "rows": rows, "first_date": first, "last_date": last,
            "satellites": dict(sorted(sats.items())),
            "versions": dict(sorted(versions.items())),
            "product": sorted({"nrt" if "NRT" in str(v).upper() else "archive" for v in versions}),
            "sensors": sorted(cells.sensor.astype(str).unique()), "fire_cell_days": len(cells),
            "filters": dict(report), "seconds": round(time.time() - t0, 1)}
    (tmp / "meta.json").write_text(json.dumps(meta, indent=2))
    shutil.rmtree(final, ignore_errors=True)
    tmp.rename(final)
    return meta


def out_root(cfg: Config) -> Path:
    return cfg.processed_dir / "archive"


def worker_args(cfg: Config) -> dict:
    return {"sensors": cfg.sensors, "aois": {a: cfg.aois[a].bbox for a in cfg.archive["aois"]},
            "fine": cfg.aggregate["fine_deg"], "coarse": cfg.clean["grid_deg"],
            "region_deg": cfg.harmonize["region_deg"], "min_conf": cfg.clean["min_confidence"],
            "chunk_rows": cfg.archive["chunk_rows"]}


def manifest_entry(path: Path, sha: str, meta: dict, root: Path) -> dict:
    stat = path.stat()
    try:
        shown = path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        shown = str(path.resolve())
    return {"path": shown, "bytes": stat.st_size, "mtime_ns": stat.st_mtime_ns, "sha256": sha,
            "source": {"provider": "NASA FIRMS", "url": FIRMS_DOWNLOAD_URL, "request": path.stem},
            **{k: meta[k] for k in ("rows", "first_date", "last_date", "satellites", "product", "versions")},
            "sensors": meta["sensors"], "ingest": {"part": sha, "fire_cell_days": meta["fire_cell_days"],
                                                   "seconds": meta["seconds"], "filters": meta["filters"]}}


def update_manifest(cfg: Config, entries: list[dict]) -> Path:
    path = cfg.data_dir / "manifest.json"
    m = json.loads(path.read_text()) if path.exists() else {"files": []}
    by_path = {e["path"]: e for e in m["files"]}
    by_path.update({e["path"]: e for e in entries})
    m["files"] = sorted(by_path.values(), key=lambda e: e["path"])
    path.write_text(json.dumps(m, indent=2) + "\n")
    return path


def run(cfg: Config, archive_dir: Path, workers: int | None = None, only: list[str] | None = None,
        merge_parts: bool = True) -> dict:
    t0 = time.time()
    zips = sorted(Path(archive_dir).glob("*.zip"))
    if only:
        zips = [z for z in zips if z.name in only]
    root = out_root(cfg) / "parts"
    root.mkdir(parents=True, exist_ok=True)
    print(f"  hashing {len(zips)} zips ...")
    shas = {z: sha256(z) for z in zips}
    entries, todo = [], []
    for z, sha in shas.items():
        meta_path = root / sha / "meta.json"
        meta = json.loads(meta_path.read_text()) if meta_path.exists() else None
        if meta is not None and meta.get("version", 1) >= PART_VERSION:
            entries.append(manifest_entry(z, sha, meta, cfg.root))
        else:
            todo.append(z)
    todo.sort(key=lambda z: -z.stat().st_size)          # biggest first balances the pool
    print(f"  {len(entries)} zips already ingested (skipped), {len(todo)} to read")
    workers = max(1, min(workers or (os.cpu_count() or 2) - 1, len(todo) or 1))
    args = worker_args(cfg)
    if todo:
        with ProcessPoolExecutor(workers) as pool:
            futures = {pool.submit(process_zip, str(z), str(root), shas[z], **args): z for z in todo}
            for f in as_completed(futures):
                z = futures[f]
                meta = f.result()
                entries.append(manifest_entry(z, shas[z], meta, cfg.root))
                update_manifest(cfg, entries)
                print(f"  {z.name}: {meta['rows']:,} rows {meta['first_date']} -> {meta['last_date']} "
                      f"{meta['sensors']} [{meta['seconds']:.0f}s, {time.time() - t0:.0f}s total]", flush=True)
    update_manifest(cfg, entries)
    result = {"zips": len(zips), "read": len(todo), "seconds_reading": round(time.time() - t0, 1)}
    if merge_parts:
        result.update(merge(cfg, [root / shas[z] for z in zips], entries))
    return result


# ---------------------------------------------------------------------------------------------------------- merge

def read_parts(dirs: list[Path], name: str) -> pd.DataFrame:
    frames = [pd.read_feather(d / f"{name}.feather") for d in dirs if (d / f"{name}.feather").exists()]
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def as_sensor(df: pd.DataFrame, sensors: list[str]) -> pd.DataFrame:
    df["sensor"] = pd.Categorical(df.sensor.astype(str), categories=sensors)
    df["acq_date"] = pd.to_datetime(df.acq_date).astype("datetime64[s]")
    return df


def check_no_overlap(cfg: Config, entries: list[dict], daily_archive: pd.DataFrame, avail_2026: pd.DataFrame) -> dict:
    """Archives end before data/raw starts, and no sensor-day comes from two zips."""
    raw_first = pd.Timestamp(avail_2026.acq_date.min())
    raw_entries = [e for e in json.loads((cfg.data_dir / "manifest.json").read_text())["files"]
                   if e["path"].startswith("data/raw")]
    if raw_entries:
        raw_first = min(raw_first, pd.Timestamp(min(e["first_date"] for e in raw_entries)))
    archive_last = pd.Timestamp(max(e["last_date"] for e in entries))
    assert archive_last < raw_first, f"archive ends {archive_last.date()} but data/raw starts {raw_first.date()}"
    dup = daily_archive.duplicated(["sensor", "acq_date"]).sum()
    assert dup == 0, f"{dup} sensor-days appear in two archive zips"
    return {"archive_last_day": str(archive_last.date()), "raw_first_day": str(raw_first.date())}


def merge(cfg: Config, dirs: list[Path], entries: list[dict]) -> dict:
    t0 = time.time()
    sensors, fine = list(cfg.sensors), cfg.aggregate["fine_deg"]
    out = out_root(cfg)
    cells26 = read_table(cfg.processed_dir, "sensor_fire_cells")
    avail26 = read_table(cfg.processed_dir, "sensor_availability")
    daily = as_sensor(read_parts(dirs, "daily"), sensors)
    overlap = check_no_overlap(cfg, entries, daily, avail26)

    # availability: rolling medians see 2026 as context; 2026 keeps the statuses it already has
    daily26 = cells26.groupby(["sensor", "acq_date"], observed=True).n_detections.sum().reset_index()
    both = pd.concat([daily, as_sensor(daily26, sensors)], ignore_index=True)
    first = pd.Timestamp(daily.acq_date.min())
    avail = availability(both, cfg.sensors, cfg.aggregate["partial_fraction"], first, pd.Timestamp(both.acq_date.max()),
                         cfg.aggregate["cross_sensor_fraction"], tuple(cfg.aggregate["cross_sensor_instruments"]))
    avail = avail[avail.acq_date < pd.Timestamp(avail26.acq_date.min())]
    avail26 = avail26.assign(acq_date=pd.to_datetime(avail26.acq_date).astype(avail.acq_date.dtype))
    avail = pd.concat([avail, avail26[avail.columns]], ignore_index=True)
    for c, cats in (("sensor", sensors), ("status", list(avail26.status.cat.categories)),
                    ("status_own_rule", list(avail26.status.cat.categories))):
        avail[c] = pd.Categorical(avail[c].astype(str), categories=cats)
    avail.reset_index(drop=True).to_feather(out / "sensor_availability.feather")

    region = pd.concat([as_sensor(read_parts(dirs, "region"), sensors),
                        sensor_grid(cells26, fine, cfg.harmonize["region_deg"])], ignore_index=True)
    region["sensor"] = pd.Categorical(region.sensor.astype(str), categories=sensors)
    region.to_feather(out / "region_daily.feather")

    tiles = build_tiles(out / "tiles", dirs, read_table(cfg.processed_dir, "sensor_grid_daily"), sensors)

    clim = n20_climatology(read_parts(dirs, "n20_weeks"))
    clim.to_feather(out / "n20_week_climatology.feather")

    aoi_reports = {name: build_aoi(cfg, name, read_parts(dirs, f"aoi_{name}"), cells26, avail)
                   for name in cfg.archive["aois"]}
    status = {f"{s}": {k: int(v) for k, v in g.status.value_counts().items() if v}
              for s, g in avail[avail.acq_date < pd.Timestamp("2026-01-01")].groupby("sensor", observed=True)}
    summary = {"overlap_check": overlap, "first_day": str(first.date()),
               "last_day": str(pd.Timestamp(avail.acq_date.max()).date()),
               "status_days_2012_2025": status, "region_rows": len(region), "tiles": tiles,
               "n20_climatology_cells": int(
                   clim[["cell_lat", "cell_lon"]].drop_duplicates().shape[0]), "aois": aoi_reports,
               "merge_seconds": round(time.time() - t0, 1)}
    (out / "ingest_report.json").write_text(json.dumps(summary, indent=2, default=str) + "\n")
    print(json.dumps({k: v for k, v in summary.items() if k != "aois"}, indent=1, default=str))
    return summary


def build_tiles(out: Path, dirs: list[Path], grid26: pd.DataFrame, sensors: list[str]) -> dict:
    """Global sensor x day x 0.25° grid, 2012-2026, one feather file per 10° tile (archive fragments + 2026)."""
    tmp = out.with_name(out.name + ".tmp")
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    by_tile = dict(tuple(grid26.groupby(tile_name(grid26.cell_lat.to_numpy(), grid26.cell_lon.to_numpy()))))
    names = sorted(set(by_tile) | {p.stem for d in dirs for p in (d / "g025").glob("*.feather")})
    rows = 0
    for name in names:
        frames = [as_sensor(pd.read_feather(d / "g025" / f"{name}.feather"), sensors) for d in dirs
                  if (d / "g025" / f"{name}.feather").exists()]
        if name in by_tile:
            frames.append(as_sensor(by_tile[name].copy(), sensors))
        df = pd.concat(frames, ignore_index=True).sort_values(["acq_date", "cell_lat", "cell_lon"])
        df["sensor"] = pd.Categorical(df.sensor.astype(str), categories=sensors)
        df.reset_index(drop=True).to_feather(tmp / f"{name}.feather", compression="zstd")
        rows += len(df)
    shutil.rmtree(out, ignore_errors=True)
    tmp.rename(out)
    return {"files": len(names), "rows": rows, "tile_deg": TILE_DEG}


def n20_climatology(weeks: pd.DataFrame) -> pd.DataFrame:
    """Fraction of the climatology years (2019-2025) with >= 1 NOAA-20 fire cell-day in each 0.25° cell and week."""
    lo, hi = CLIMATOLOGY_YEARS
    w = weeks[weeks.year.between(lo, hi)].drop_duplicates()
    n_years = hi - lo + 1
    out = w.groupby(["cell_lat", "cell_lon", "week"]).year.nunique().rename("years_with_fire").reset_index()
    out["p_years"] = (out.years_with_fire / n_years).astype(np.float32)
    out.attrs["years"] = f"{lo}-{hi}"
    return out


def build_aoi(cfg: Config, name: str, archive_cells: pd.DataFrame, cells26: pd.DataFrame, avail: pd.DataFrame) -> dict:
    from godseye.ingest.aoi import gate_summary
    from godseye.ingest.coverage import plot_coverage

    aoi, fine, sensors = cfg.aois[name], cfg.aggregate["fine_deg"], list(cfg.sensors)
    lat, lon = cell_centres(cells26, fine)
    cells = pd.concat([as_sensor(archive_cells, sensors), cells26[inside_bbox(lat, lon, aoi.bbox).to_numpy()]],
                      ignore_index=True)
    cells["sensor"] = pd.Categorical(cells.sensor.astype(str), categories=sensors)
    cells = cells.sort_values(CELL_KEYS).reset_index(drop=True)
    grid = sensor_grid(cells, fine, cfg.clean["grid_deg"])
    a = avail.assign(basis="global")
    d = cfg.processed_dir / "aoi" / name
    d.mkdir(parents=True, exist_ok=True)
    cells.to_feather(d / "sensor_fire_cells.feather")
    grid.to_feather(d / "sensor_grid_daily.feather")
    a.reset_index(drop=True).to_feather(d / "sensor_availability.feather")
    fig = plot_coverage(a, cfg.figures_dir / f"coverage_{name}.png", f"{cfg.display_name}: {aoi.label}, coverage")
    years = {s: sorted({int(y) for y in pd.to_datetime(cells[cells.sensor.astype(str) == s].acq_date).dt.year})
             for s in sensors}
    report = {"aoi": name, "bbox": list(aoi.bbox), "first_day": str(pd.Timestamp(cells.acq_date.min()).date()),
              "last_day": str(pd.Timestamp(cells.acq_date.max()).date()),
              "years_per_sensor": {s: (f"{y[0]}-{y[-1]} ({len(y)} years)" if y else "none") for s, y in years.items()},
              "fire_cell_days": {str(k): int(v) for k, v in cells.groupby("sensor", observed=True).size().items()},
              "coverage_chart": str(fig), "gate": gate_summary(cfg, grid, a, aoi)}
    nested = {n: gate_summary(cfg, grid, a, cfg.aois[n]) for n, o in cfg.aois.items()
              if n != name and inside_bbox(pd.Series([o.bbox[1], o.bbox[3]]), pd.Series([o.bbox[0], o.bbox[2]]),
                                           aoi.bbox).all()}
    if nested:
        report["nested_gates"] = nested
    (d / "ingest_report.json").write_text(json.dumps(report, indent=2, default=str) + "\n")
    print(f"  {name}: {report['first_day']} -> {report['last_day']}, gate {report['gate']['status']}")
    return report
