"""
`godseye ingest --aoi NAME` (ticket 07): a multi-year record for one AOI from the FIRMS archive downloads.

  inputs     the archive folder (read in place, never moved or copied) and the 2026 files in data/raw, both filtered to
             the AOI's bbox while reading
  dedupe     the cleaning rules apply to both together: for a satellite-day present in both an archive (standard) and
             an NRT file, the archive wins; identical satellite + time + location rows are kept once
  output     data/processed/aoi/<name>/: fires_clean, sensor_fire_cells, sensor_grid_daily, sensor_availability, a
             coverage chart (sensor x day) and ingest_report.json
  availability  an AOI-only download cannot show outages (a fire-free AOI day is a real zero), so days outside the
             global data take their status from the sensors' operating dates only (basis "aoi_archive"); days the
             global data covers reuse the global status (basis "global")
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
import pandas as pd

from godseye.clean import pipeline as clean
from godseye.clean.io import read_table, write_table
from godseye.config import Config, Sensor
from godseye.ingest.aggregate import COVERAGE_GAP, STATUSES, fire_cells, sensor_grid
from godseye.ingest.coverage import plot_coverage
from godseye.ingest.pipeline import COLUMNS


def aoi_availability(cells: pd.DataFrame, sensors: dict[str, Sensor], global_avail: pd.DataFrame | None,
                     first: pd.Timestamp, last: pd.Timestamp) -> pd.DataFrame:
    dates = pd.date_range(first, last, freq="D")
    days = dates.to_numpy().astype("datetime64[D]")
    g = None
    if global_avail is not None and len(global_avail):
        g = global_avail.assign(sensor=global_avail.sensor.astype(str), status=global_avail.status.astype(str))
        g = g.set_index(["sensor", pd.to_datetime(g.acq_date).dt.normalize()]).status
    frames = []
    for name, s in sensors.items():
        mine = cells[cells.sensor.astype(str) == name]
        start = pd.Timestamp(s.start) if s.start is not None else (
            pd.Timestamp(mine.acq_date.min()) if len(mine) else None)
        operational = np.ones(len(dates), bool)
        if start is not None:
            operational &= dates >= start
        else:
            operational[:] = False
        if s.end is not None:
            operational &= dates <= pd.Timestamp(s.end)
        status = np.where(operational, "ok", "not_operational").astype(object)
        basis = np.full(len(dates), "aoi_archive", dtype=object)
        if g is not None:
            known = g.reindex(pd.MultiIndex.from_arrays([[name] * len(dates), dates])).to_numpy()
            has = pd.notna(known)
            status = np.where(has, known, status)
            basis = np.where(has, "global", basis)
        frames.append(pd.DataFrame({"sensor": name, "acq_date": days, "status": status, "basis": basis}))
    out = pd.concat(frames, ignore_index=True)
    out["sensor"] = pd.Categorical(out.sensor, categories=list(sensors))
    out["status"] = pd.Categorical(out.status, categories=STATUSES)
    out["status_own_rule"] = out.status
    out["n_detections_global"] = -1          # not known for AOI-only data
    out["is_coverage_gap"] = out.status.isin(COVERAGE_GAP)
    return out


def run(cfg: Config, aoi_name: str, archive_dir: Path, out_dir: Path | None = None) -> dict:
    t0 = time.time()
    if aoi_name not in cfg.aois:
        raise SystemExit(f"unknown AOI {aoi_name!r}; known: {sorted(cfg.aois)}")
    aoi = cfg.aois[aoi_name]
    out_dir = Path(out_dir or cfg.processed_dir / "aoi" / aoi_name)
    inputs = [str(p) for p in (archive_dir, cfg.raw_dir) if Path(p).exists()]
    report = clean.run(inputs, out_dir, min_confidence=cfg.clean["min_confidence"], grid_deg=cfg.clean["grid_deg"],
                       recent_days=cfg.clean["recent_days"], table_format=cfg.clean["table_format"], bbox=aoi.bbox)
    det = read_table(out_dir, "fires_clean", COLUMNS)
    fine, coarse = cfg.aggregate["fine_deg"], cfg.clean["grid_deg"]
    cells = fire_cells(det, cfg.sensors, fine)
    grid = sensor_grid(cells, fine, coarse)
    global_path = cfg.processed_dir / "sensor_availability.feather"
    global_avail = pd.read_feather(global_path) if global_path.exists() else None
    avail = aoi_availability(cells, cfg.sensors, global_avail, pd.Timestamp(cells.acq_date.min()),
                             pd.Timestamp(cells.acq_date.max()))
    for table, name in ((cells, "sensor_fire_cells"), (grid, "sensor_grid_daily"), (avail, "sensor_availability")):
        write_table(table, out_dir / name, "feather")
    fig = plot_coverage(avail.assign(n_detections_global=0), cfg.figures_dir / f"coverage_{aoi_name}.png",
                        f"{cfg.display_name}: {aoi.label}, coverage by sensor")
    years = {s: sorted({int(y) for y in pd.to_datetime(cells[cells.sensor.astype(str) == s].acq_date).dt.year})
             for s in cfg.sensors}
    result = {
        "aoi": aoi_name, "bbox": list(aoi.bbox), "inputs": inputs,
        "first_day": str(pd.Timestamp(cells.acq_date.min()).date()),
        "last_day": str(pd.Timestamp(cells.acq_date.max()).date()),
        "years_per_sensor": {s: (f"{y[0]}-{y[-1]} ({len(y)} years)" if y else "none") for s, y in years.items()},
        "earliest_year": {s: (y[0] if y else None) for s, y in years.items()},
        "detections_kept": report["output_rows"], "rows_outside_aoi": report.get("rows_outside_aoi", 0),
        "dropped_nrt_superseded_by_archive": report.get("dropped_nrt_superseded_by_archive", 0),
        "dropped_duplicates": report.get("dropped_duplicates", 0),
        "fire_cell_days": {str(k): int(v) for k, v in cells.groupby("sensor", observed=True).size().items()},
        "coverage_chart": str(fig),
    }
    result["gate"] = gate_summary(cfg, grid, avail, aoi)
    (out_dir / "ingest_report.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: result[k] for k in ("aoi", "first_day", "last_day", "years_per_sensor", "detections_kept",
                                              "dropped_nrt_superseded_by_archive", "dropped_duplicates")}, indent=1))
    print(f"  wrote {out_dir}  [{time.time() - t0:.0f}s]")
    return result


def gate_summary(cfg: Config, grid: pd.DataFrame, avail: pd.DataFrame, aoi) -> dict:
    """ADR 0006 numbers for the ingest report: years of history and weeks passing each gate rule, on the harmonized
    series when the links exist (else the reference sensor's raw series)."""
    from godseye.calendar import climatology as C
    from godseye.calendar.harmonized import build_chain
    from godseye.calendar.store import CalendarStore
    from godseye.harmonize import pipeline as harmonize

    store = CalendarStore(grid, avail, cfg.clean["grid_deg"])
    series = "harmonized"
    if (cfg.processed_dir / harmonize.REPORT).exists():
        store.attach_chain(build_chain(cfg.harmonize["headline"], harmonize.load(cfg.processed_dir),
                                       cfg.harmonize["region_deg"]))
    h = store.harmonized(aoi.bbox, "week")
    cal = store.calendar(aoi.bbox, "cell_days", "week")
    if h is None:
        series = cfg.risk_v2["reference_sensor"]
        i = store.sensors.index(series)
        values, coverage, days = cal.values[i], cal.coverage[i], cal.data_days[i]
    else:
        values, coverage, days = h.values, h.coverage, h.data_days
    a = C.analyse(cal.years, values, coverage, days, cfg.climatology["activity"])
    return {"series": series, "history_years": a.history_years, "status": a.status, "message": a.message,
            "rule": a.gate_rule, "gated_weeks": len(a.gated_weeks), "counts": a.gate_counts,
            "activity": a.activity, "active_threshold": a.active_threshold}
