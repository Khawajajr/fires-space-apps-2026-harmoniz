"""Paired weekly series for a sensor link: region x week totals of sensor x and reference sensor y.

Only days when BOTH sensors delivered full data (status ok) are used, so outages and partial days never look like a
sensor difference. Regions are square blocks of `region_deg` degrees. Weeks start on Monday; each week belongs to the
calendar month of its Thursday (the ISO rule), which is the unit left out in cross-validation.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def region_of(lat: np.ndarray, lon: np.ndarray, region_deg: float) -> np.ndarray:
    """Region id 'lat0,lon0' (south-west corner) of each coordinate."""
    rlat = (np.floor(np.asarray(lat) / region_deg) * region_deg).astype(int)
    rlon = (np.floor(np.asarray(lon) / region_deg) * region_deg).astype(int)
    return np.char.add(np.char.add(rlat.astype(str), ","), rlon.astype(str))


def paired_days(avail: pd.DataFrame, x: str, y: str, status_column: str = "status") -> pd.DatetimeIndex:
    """Days both sensors were 'ok'. status_column="status_own_rule" ignores the cross-sensor check (sensitivity)."""
    ok = avail[avail[status_column].astype(str) == "ok"]
    days = set(ok[ok.sensor.astype(str) == x].acq_date) & set(ok[ok.sensor.astype(str) == y].acq_date)
    return pd.DatetimeIndex(sorted(days))


def weekly_pairs(grid: pd.DataFrame, days: pd.DatetimeIndex, x: str, y: str, region_deg: float,
                 metric: str = "n_fire_cells") -> pd.DataFrame:
    """Columns: region, week (Monday), month (YYYY-MM of the week's Thursday), season (DJF..SON), x, y."""
    g = grid[grid.sensor.astype(str).isin([x, y]) & grid.acq_date.isin(days)]
    week = g.acq_date - pd.to_timedelta(g.acq_date.dt.weekday, unit="D")
    t = pd.DataFrame({"region": region_of(g.cell_lat.to_numpy(), g.cell_lon.to_numpy(), region_deg),
                      "week": week.to_numpy(), "sensor": g.sensor.astype(str).to_numpy(),
                      "v": g[metric].to_numpy(np.float64)})
    wide = t.pivot_table(index=["region", "week"], columns="sensor", values="v", aggfunc="sum", fill_value=0.0)
    wide = wide.reindex(columns=[x, y], fill_value=0.0).rename(columns={x: "x", y: "y"}).reset_index()
    wide.columns.name = None
    thursday = wide.week + pd.Timedelta(days=3)
    wide["month"] = thursday.dt.strftime("%Y-%m")
    wide["season"] = np.array(["DJF", "DJF", "MAM", "MAM", "MAM", "JJA", "JJA", "JJA", "SON", "SON", "SON", "DJF"]
                              )[thursday.dt.month.to_numpy() - 1]
    return wide[(wide.x > 0) | (wide.y > 0)].reset_index(drop=True)
