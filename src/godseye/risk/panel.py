"""
Dense cell x day panel built from `fires_daily_grid`, and the per-cell features as of an issue date t.

Feature groups (all computed only from data on or before t - no leakage):
  history     fire-day counts over 7/14/30/90 days, long-run fire frequency, detection counts
  intensity   rolling FRP sum / mean / max
  diurnal     night-detection ratio (night burning = drier fuels, persistent fires)
  dry-spell   PROXIES ONLY - there is no weather data in FIRMS: days since last fire,
              current consecutive burning streak, 7d-vs-30d acceleration, and mean background
              11 um brightness temperature (MODIS T31 / VIIRS I5) of detections, a surface heat proxy.
  spatial     fire days in the 8 neighbouring cells, cell lat/lon
  seasonal    sin/cos day-of-year of the issue date
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from godseye.clean.io import find_table, read_table_file
from godseye.config import get_config

HORIZON_DAYS = get_config().risk["horizon_days"]
FEATURES = [
    "fire_days_7", "fire_days_14", "fire_days_30", "fire_days_90", "fire_freq_hist",
    "det_7", "det_30", "frp_sum_7", "frp_sum_30", "frp_mean_30", "frp_max_30",
    "night_ratio_30", "days_since_fire", "fire_streak", "accel_7_30", "bt31_mean_7",
    "nbr_fire_days_7", "nbr_fire_days_30", "cell_lat", "cell_lon", "doy_sin", "doy_cos",
]


def load_grid(path: Path | None = None) -> pd.DataFrame:
    if path is None:
        path = find_table(get_config().processed_dir, "fires_daily_grid")
    grid = read_table_file(path)
    grid["acq_date"] = pd.to_datetime(grid["acq_date"])
    return grid


class Panel:
    """Dense (cell x day) matrices built from the sparse daily grid."""

    def __init__(self, grid: pd.DataFrame, grid_deg: float):
        self.grid_deg = grid_deg
        self.dates = pd.date_range(grid.acq_date.min(), grid.acq_date.max(), freq="D")
        cells = grid[["cell_lat", "cell_lon"]].drop_duplicates().sort_values(["cell_lat", "cell_lon"])
        self.cells = cells.reset_index(drop=True)
        cell_idx = pd.MultiIndex.from_frame(self.cells).get_indexer(
            pd.MultiIndex.from_frame(grid[["cell_lat", "cell_lon"]]))
        day_idx = (grid.acq_date - self.dates[0]).dt.days.to_numpy()
        shape = (len(self.cells), len(self.dates))

        def mat(values, fill=0.0):
            m = np.full(shape, fill, dtype=np.float32)
            m[cell_idx, day_idx] = values
            return m

        self.fire = mat(1.0)
        self.det = mat(grid.n_detections.to_numpy())
        self.frp_sum = mat(grid.frp_sum_mw.to_numpy())
        self.frp_max = mat(grid.frp_max_mw.to_numpy())
        self.night = mat(grid.n_night.to_numpy())
        bt31 = mat(grid.bt31_mean_k.to_numpy(), fill=np.nan)
        self.bt31_sum, self.bt31_n = np.nan_to_num(bt31), (~np.isnan(bt31)).astype(np.float32)
        # Cumulative sums with a leading zero column: window (t-w, t] = cs[:, t+1] - cs[:, t+1-w].
        self.cs = {k: np.concatenate([np.zeros((shape[0], 1), np.float32),
                                      np.cumsum(getattr(self, k), axis=1, dtype=np.float32)], axis=1)
                   for k in ("fire", "det", "frp_sum", "night", "bt31_sum", "bt31_n")}
        self.first_fire = self.fire.argmax(axis=1)
        self.rows = np.floor((self.cells.cell_lat.to_numpy() + 90) / grid_deg).astype(int)
        self.cols = np.floor((self.cells.cell_lon.to_numpy() + 180) / grid_deg).astype(int)

    def window(self, key: str, t: int, w: int) -> np.ndarray:
        return self.cs[key][:, t + 1] - self.cs[key][:, max(0, t + 1 - w)]

    def neighbours(self, values: np.ndarray) -> np.ndarray:
        """Sum of `values` over the 8 surrounding grid cells (self excluded)."""
        h, w = int(round(180 / self.grid_deg)), int(round(360 / self.grid_deg))
        g = np.zeros((h + 2, w + 2), np.float32)
        g[self.rows + 1, self.cols + 1] = values
        total = sum(g[1 + dr:h + 1 + dr, 1 + dc:w + 1 + dc]
                    for dr in (-1, 0, 1) for dc in (-1, 0, 1) if (dr, dc) != (0, 0))
        return total[self.rows, self.cols]

    def features(self, t: int) -> pd.DataFrame:
        """Feature table for every cell that has burned on or before day index t."""
        f = {}
        for w in (7, 14, 30, 90):
            f[f"fire_days_{w}"] = self.window("fire", t, w)
        f["fire_freq_hist"] = self.cs["fire"][:, t + 1] / (t + 1)
        f["det_7"], f["det_30"] = self.window("det", t, 7), self.window("det", t, 30)
        f["frp_sum_7"], f["frp_sum_30"] = self.window("frp_sum", t, 7), self.window("frp_sum", t, 30)
        with np.errstate(divide="ignore", invalid="ignore"):
            f["frp_mean_30"] = np.where(f["det_30"] > 0, f["frp_sum_30"] / f["det_30"], 0)
            f["night_ratio_30"] = np.where(f["det_30"] > 0, self.window("night", t, 30) / f["det_30"], np.nan)
            bt_n = self.window("bt31_n", t, 7)
            f["bt31_mean_7"] = np.where(bt_n > 0, self.window("bt31_sum", t, 7) / bt_n, np.nan)
        f["frp_max_30"] = self.frp_max[:, max(0, t - 29):t + 1].max(axis=1)

        past = self.fire[:, :t + 1][:, ::-1]           # column 0 = day t
        burned = past.max(axis=1) > 0
        f["days_since_fire"] = np.where(burned, past.argmax(axis=1), 365).astype(np.float32)
        f["fire_streak"] = np.where(past[:, 0] > 0, (past == 0).argmax(axis=1), 0).astype(np.float32)
        f["fire_streak"][(past > 0).all(axis=1)] = t + 1
        f["accel_7_30"] = f["fire_days_7"] / (f["fire_days_30"] * 7 / 30 + 1)

        f["nbr_fire_days_7"] = self.neighbours(f["fire_days_7"])
        f["nbr_fire_days_30"] = self.neighbours(f["fire_days_30"])
        f["cell_lat"], f["cell_lon"] = self.cells.cell_lat.to_numpy(), self.cells.cell_lon.to_numpy()
        doy = self.dates[t].dayofyear
        f["doy_sin"] = np.full(len(self.cells), np.sin(2 * np.pi * doy / 365.25), np.float32)
        f["doy_cos"] = np.full(len(self.cells), np.cos(2 * np.pi * doy / 365.25), np.float32)

        out = pd.DataFrame(f)[FEATURES].astype(np.float32)
        out["t"] = t
        out["cell_id"] = np.arange(len(self.cells))
        return out[self.first_fire <= t].reset_index(drop=True)

    def label(self, t: int, cell_id: np.ndarray) -> np.ndarray:
        return (self.window("fire", t + HORIZON_DAYS, HORIZON_DAYS)[cell_id] > 0).astype(np.int8)
