"""
Per-sensor daily aggregates (never summed across sensors) and sensor availability.

  fire cells   sensor x day x 0.01° cell: one row per fire cell-day, with its detection count
  sensor grid  sensor x day x coarse cell: detections and the number of distinct fire cells inside it,
               so the fire cell-days of any AOI made of coarse cells are a sum over its cells
  availability sensor x day: ok | partial | no_data | not_operational, plus is_coverage_gap, so missing data is
               never read as zero fire

All counts are of detections kept by `clean` (nominal+ confidence, vegetation fires), not of every FIRMS record.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from godseye.config import Sensor

STATUSES = ["ok", "partial", "no_data", "not_operational"]
COVERAGE_GAP = {"partial", "no_data", "not_operational"}   # glossary: coverage gap


def _days(acq_date: pd.Series) -> np.ndarray:
    """acq_date (categorical or plain 'YYYY-MM-DD' strings) -> datetime64[D], converting each distinct value once."""
    cat = acq_date.astype("category")
    lookup = pd.to_datetime(cat.cat.categories.astype(str)).to_numpy().astype("datetime64[D]")
    return lookup[cat.cat.codes.to_numpy()]


def cell_index(deg: np.ndarray, size: float) -> np.ndarray:
    """Grid index of each coordinate. Rounding first keeps exact boundaries (e.g. -81.79 at 0.01°) in their own cell."""
    return np.floor(np.round(deg / size, 6)).astype(np.int32)


def fire_cells(det: pd.DataFrame, sensors: dict[str, Sensor], fine_deg: float) -> pd.DataFrame:
    """Cleaned detections -> one row per (sensor, day, fine cell) with at least one detection."""
    by_satellite = {s.satellite: s.name for s in sensors.values()}
    sensor = det.satellite.astype(str).map(by_satellite)
    if sensor.isna().any():
        unknown = sorted(det.satellite.astype(str)[sensor.isna()].unique())
        raise ValueError(f"satellites with no sensor in configs/pipeline.yaml: {unknown}")
    g = pd.DataFrame({
        "sensor": pd.Categorical(sensor, categories=list(sensors)),
        "acq_date": _days(det.acq_date),
        "lat_i": cell_index(det.latitude.to_numpy(), fine_deg),
        "lon_i": cell_index(det.longitude.to_numpy(), fine_deg),
        "frp_mw": det.frp_mw.to_numpy(np.float64),
        "is_daytime": (det.daynight.astype(str) == "D").to_numpy(np.int32),
    })
    out = (g.groupby(["sensor", "acq_date", "lat_i", "lon_i"], sort=True, observed=True)
            .agg(n_detections=("frp_mw", "size"), n_detections_daytime=("is_daytime", "sum"),
                 frp_sum_mw=("frp_mw", "sum"))
            .reset_index())
    out["n_detections"] = out.n_detections.astype(np.int32)
    out["n_detections_daytime"] = out.n_detections_daytime.astype(np.int32)
    out["frp_sum_mw"] = out.frp_sum_mw.astype(np.float32)
    return out


def sensor_grid(cells: pd.DataFrame, fine_deg: float, coarse_deg: float) -> pd.DataFrame:
    """Fire cells -> (sensor, day, coarse cell): detections, distinct fire cells, and those with a daytime detection."""
    ratio = round(coarse_deg / fine_deg)
    if abs(ratio * fine_deg - coarse_deg) > 1e-9:
        raise ValueError(f"coarse grid {coarse_deg} must be a whole multiple of the fine grid {fine_deg}")
    ci = np.floor_divide(cells.lat_i.to_numpy(), ratio)
    cj = np.floor_divide(cells.lon_i.to_numpy(), ratio)
    g = pd.DataFrame({
        "sensor": cells.sensor, "acq_date": cells.acq_date,
        "cell_lat": ((ci + 0.5) * coarse_deg).round(4), "cell_lon": ((cj + 0.5) * coarse_deg).round(4),
        "n_detections": cells.n_detections, "is_daytime_cell": (cells.n_detections_daytime > 0).astype(np.int32),
        "frp_sum_mw": cells.frp_sum_mw,
    })
    out = (g.groupby(["sensor", "acq_date", "cell_lat", "cell_lon"], sort=True, observed=True)
            .agg(n_detections=("n_detections", "sum"), n_fire_cells=("n_detections", "size"),
                 n_fire_cells_daytime=("is_daytime_cell", "sum"), frp_sum_mw=("frp_sum_mw", "sum"))
            .reset_index())
    for c in ("n_detections", "n_fire_cells", "n_fire_cells_daytime"):
        out[c] = out[c].astype(np.int32)
    return out


def availability(cells: pd.DataFrame, sensors: dict[str, Sensor], partial_fraction: float,
                 first: pd.Timestamp | None = None, last: pd.Timestamp | None = None) -> pd.DataFrame:
    """
    Per sensor and day over [first, last] (default: the data's range), from GLOBAL detections:
      not_operational  outside the sensor's configured start/end (start unset: before its first data day)
      no_data          zero detections worldwide (an outage: the world always has fires)
      partial          fewer than partial_fraction x the sensor's centred 31-day median
      ok               otherwise
    """
    daily = cells.groupby(["sensor", "acq_date"], observed=True).n_detections.sum()
    first = pd.Timestamp(first if first is not None else cells.acq_date.min())
    last = pd.Timestamp(last if last is not None else cells.acq_date.max())
    dates = pd.date_range(first, last, freq="D")
    frames = []
    for name, s in sensors.items():
        n = (daily.xs(name, level="sensor") if name in daily.index.get_level_values(0) else pd.Series(dtype=float))
        n = n.reindex(dates.to_numpy().astype("datetime64[D]"), fill_value=0).to_numpy()
        operational = np.ones(len(dates), bool)
        start = pd.Timestamp(s.start) if s.start is not None else (dates[n > 0][0] if (n > 0).any() else None)
        if start is not None:
            operational &= dates >= start
        if s.end is not None:
            operational &= dates <= pd.Timestamp(s.end)
        median = pd.Series(np.where(operational, n, np.nan)).rolling(31, center=True, min_periods=7).median()
        status = np.select(
            [~operational, n == 0, n < partial_fraction * median.to_numpy()],
            ["not_operational", "no_data", "partial"], default="ok")
        frames.append(pd.DataFrame({"sensor": name, "acq_date": dates.to_numpy().astype("datetime64[D]"),
                                    "n_detections_global": n.astype(np.int64), "status": status}))
    out = pd.concat(frames, ignore_index=True)
    out["sensor"] = pd.Categorical(out.sensor, categories=list(sensors))
    out["status"] = pd.Categorical(out.status, categories=STATUSES)
    out["is_coverage_gap"] = out.status.isin(COVERAGE_GAP)
    out["basis"] = "global"
    return out
