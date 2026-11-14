"""
Ticket 08: calibrate the sensor links on the global multi-year record (ADR 0001).

With `godseye ingest-archive` done, every link is fitted on data/processed/archive/region_daily (sensor x day x 10°
block fire cell-days, 2012-2026) and the matching availability: the VIIRS continuity links on their whole overlap,
the headline link (S-NPP -> Aqua-MODIS) on its `window` (2013-2021: Aqua's original orbit). With >= 3 years the folds
are years, so month effects are validated and the headline link is no longer provisional. Without the archive every
link falls back to the 2026 global data, as before.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from godseye.calendar.harmonized import row_ratios
from godseye.clean.io import read_table
from godseye.config import Config
from godseye.harmonize.link import Link
from godseye.harmonize.series import paired_days

MIN_YEARS = 3


def record_dir(processed: Path) -> Path:
    return processed / "archive"


def load_record(processed: Path, metric: str) -> tuple[pd.DataFrame, pd.DataFrame] | None:
    d = record_dir(processed)
    if not (d / "region_daily.feather").exists():
        return None
    grid = read_table(d, "region_daily", ["sensor", "acq_date", "cell_lat", "cell_lon", metric])
    grid["acq_date"] = pd.to_datetime(grid.acq_date)
    avail = read_table(d, "sensor_availability")
    avail["acq_date"] = pd.to_datetime(avail.acq_date)
    return grid, avail


def in_window(days: pd.DatetimeIndex, window: list[int] | None) -> pd.DatetimeIndex:
    return days if not window else days[(days.year >= window[0]) & (days.year <= window[1])]


def archive_dirs(cfg: Config, processed: Path) -> list[Path]:
    """Ingested multi-year AOI stores (data/processed/aoi/<name>/)."""
    return [d for d in sorted((processed / "aoi").glob("*/")) if d.name in cfg.aois
            and (d / "sensor_grid_daily.feather").exists()]


def drift_check(grid: pd.DataFrame, avail: pd.DataFrame, link: Link, metric: str, region_deg: float,
                from_year: int) -> dict:
    """Per year: target observed / the link's prediction from the source, globally, on days both delivered full
    data. A ratio drifting away from 1 after the calibration window is Aqua's orbit drift; the trend is a least-squares
    slope per year over the years from `from_year`."""
    days = paired_days(avail, link.source, link.target)
    g = grid[grid.acq_date.isin(days)]
    src, tgt = g[g.sensor.astype(str) == link.source], g[g.sensor.astype(str) == link.target]
    r = row_ratios(link, src.cell_lat.to_numpy(), src.cell_lon.to_numpy(), src.acq_date.dt.month.to_numpy(),
                   region_deg)
    pred = pd.Series(src[metric].to_numpy() * r, index=src.acq_date.dt.year.to_numpy()).groupby(level=0).sum()
    obs = tgt.groupby(tgt.acq_date.dt.year)[metric].sum()
    n = pd.Series(days.year).value_counts()
    rows = [{"year": int(y), "paired_days": int(n.get(y, 0)), "observed": round(float(obs.get(y, 0.0)), 1),
             "predicted": round(float(pred.get(y, 0.0)), 1),
             "observed_over_predicted": round(float(obs.get(y, 0.0) / pred[y]), 4) if pred.get(y, 0) else None}
            for y in sorted(set(pred.index) | set(obs.index))]
    after = [(r["year"], r["observed_over_predicted"]) for r in rows
             if r["year"] >= from_year and r["observed_over_predicted"] is not None]
    trend = None
    if len(after) >= 2:
        x, y = np.array(after, dtype=float).T
        trend = round(float(np.polyfit(x, y, 1)[0]), 4)
    inside = [r["observed_over_predicted"] for r in rows if r["year"] < from_year and r["observed_over_predicted"]]
    # Monthly from the drift years on: shows whether a shortfall is a data-quality step (FIRMS switches from archive to
    # near-real-time files in the latest months) or a gradual change such as orbit drift.
    month = lambda d: d.dt.strftime("%Y-%m")
    late_src, late_tgt = src[src.acq_date.dt.year >= from_year], tgt[tgt.acq_date.dt.year >= from_year]
    late_r = r[(src.acq_date.dt.year >= from_year).to_numpy()]
    mp = pd.Series(late_src[metric].to_numpy() * late_r,
                   index=month(late_src.acq_date).to_numpy()).groupby(level=0).sum()
    mo = late_tgt.groupby(month(late_tgt.acq_date))[metric].sum()
    monthly = [{"month": m, "observed_over_predicted": round(float(mo.get(m, 0.0) / mp[m]), 4)}
               for m in mp.index if mp[m] > 0]
    return {"years": rows, "monthly_after_window": monthly, "from_year": from_year,
            "trend_per_year_after_window": trend,
            "mean_ratio_in_window": round(float(np.mean(inside)), 4) if inside else None,
            "mean_ratio_after_window": round(float(np.mean([v for _, v in after])), 4) if after else None}
