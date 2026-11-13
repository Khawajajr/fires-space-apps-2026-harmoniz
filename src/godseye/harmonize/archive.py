"""
Ticket 08: calibrate the headline link on the archive's pre-drift years (ADR 0001).

The headline link (S-NPP -> Aqua-MODIS) prefers years when Aqua flew its original ~13:30 orbit: the configured window
(2013-2021) intersected with the years the ingested AOI archives actually cover (2018-2021 with the current
downloads). It is validated by leaving one year out (>= 3 years), so month effects are tested and may ship, and the
link is no longer provisional. Without enough archive years it falls back to the provisional 2026 fit.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from godseye.calendar.harmonized import row_ratios
from godseye.calendar.store import in_bbox
from godseye.clean.io import read_table
from godseye.config import Config
from godseye.harmonize.link import Link
from godseye.harmonize.series import paired_days, weekly_pairs

MIN_YEARS = 3


def archive_dirs(cfg: Config, processed: Path) -> list[Path]:
    """Ingested AOI stores, skipping AOIs that lie inside another ingested one (Jordan inside the Levant)."""
    dirs = [d for d in sorted((processed / "aoi").glob("*/")) if d.name in cfg.aois
            and (d / "sensor_grid_daily.feather").exists()]
    boxes = {d.name: cfg.aois[d.name].bbox for d in dirs}

    def inside(a, b):
        return a != b and boxes[b][0] <= boxes[a][0] and boxes[a][2] <= boxes[b][2] \
            and boxes[b][1] <= boxes[a][1] and boxes[a][3] <= boxes[b][3]
    return [d for d in dirs if not any(inside(d.name, o) for o in boxes)]


def pre_drift_pairs(cfg: Config, processed: Path, spec: dict, metric: str) -> tuple[pd.DataFrame, list[str]]:
    """Weekly pairs from the AOI archives, restricted to the link's calibration window (spec["prefer_archive"]);
    regions are kept per AOI."""
    lo, hi = spec["prefer_archive"]["window"]
    frames, used = [], []
    for d in archive_dirs(cfg, processed):
        grid = read_table(d, "sensor_grid_daily", ["sensor", "acq_date", "cell_lat", "cell_lon", metric])
        avail = read_table(d, "sensor_availability")
        days = paired_days(avail, spec["source"], spec["target"])
        days = days[(days.year >= lo) & (days.year <= hi)]
        if len(days):
            frames.append(weekly_pairs(grid, days, spec["source"], spec["target"], cfg.harmonize["region_deg"],
                                       metric).assign(region=lambda x, n=d.name: n + ":" + x.region))
            used.append(d.name)
    if not frames:
        return pd.DataFrame(), used
    df = pd.concat(frames, ignore_index=True)
    df = df[df.week.dt.year.between(lo, hi)]
    return df, used


def years_of(df: pd.DataFrame) -> list[int]:
    return sorted({int(m[:4]) for m in df.month}) if len(df) else []


def drift_check(cfg: Config, processed: Path, link: Link, metric: str, from_year: int) -> list[dict]:
    """Per year from `from_year`: Aqua observed / the link's prediction from S-NPP, on AOI archive days both
    delivered. Drift in Aqua's orbit shows up as a trend here."""
    rows = []
    for d in archive_dirs(cfg, processed):
        grid = read_table(d, "sensor_grid_daily", ["sensor", "acq_date", "cell_lat", "cell_lon", metric])
        avail = read_table(d, "sensor_availability")
        days = paired_days(avail, link.source, link.target)
        days = days[days.year >= from_year]
        g = grid[grid.acq_date.isin(days) & in_bbox(grid.cell_lat, grid.cell_lon, cfg.aois[d.name].bbox)]
        src = g[g.sensor.astype(str) == link.source]
        tgt = g[g.sensor.astype(str) == link.target]
        r = row_ratios(link, src.cell_lat.to_numpy(), src.cell_lon.to_numpy(), src.acq_date.dt.month.to_numpy(),
                       cfg.harmonize["region_deg"])
        pred = pd.Series(src[metric].to_numpy() * r, index=src.acq_date.dt.year.to_numpy()).groupby(level=0).sum()
        obs = tgt.groupby(tgt.acq_date.dt.year)[metric].sum()
        for y in sorted(set(pred.index) | set(obs.index)):
            p, o = float(pred.get(y, 0.0)), float(obs.get(y, 0.0))
            rows.append({"aoi": d.name, "year": int(y), "observed": round(o, 1), "predicted": round(p, 1),
                         "observed_over_predicted": round(o / p, 3) if p else None})
    return rows


def regionless(link: Link) -> Link:
    """Archive regions are 'aoi:lat,lon'; the calendar looks ratios up by plain 'lat,lon'. Strip the AOI prefix (AOIs
    used for calibration don't overlap, so a region id is unique without it)."""
    c = link.coefficients.copy()
    c["region"] = c.region.astype(str).str.split(":").str[-1]
    link.coefficients = c
    return link


def summary(df: pd.DataFrame, used: list[str], window: list[int]) -> dict:
    ys = years_of(df)
    return {"calibration_source": "AOI archives", "calibration_aois": used,
            "calibration_window": f"{ys[0]}-{ys[-1]}" if ys else None, "calibration_years": ys,
            "configured_window": f"{window[0]}-{window[1]}", "region_weeks": int(len(df)),
            "paired_days_per_year": {int(y): int(n) for y, n in
                                     df.groupby(df.week.dt.year).week.nunique().mul(7).items()} if len(df) else {}}


def enough(df: pd.DataFrame) -> bool:
    return len(years_of(df)) >= MIN_YEARS and np.isfinite(df.x.sum()) and df.x.sum() > 0
