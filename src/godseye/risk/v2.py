"""
Risk model v2 (ADRs 0004, 0005): NOAA-20 reference label and features, three time-ordered blocks.

  label      a 0.25° cell is positive at issue date t if NOAA-20 saw >= 1 fire cell-day in it during t+1..t+7
  features   from NOAA-20 only, all from data on or before t: fire days (7/14/30/90), share of past days with fire,
             fire cells and detections (7/30), FRP (7/30, mean), night share of fire cells, days since fire, current
             streak, 7d-vs-30d acceleration, fire days in the 8 neighbouring cells (7/30), cell lat/lon, and NOAA-20
             outage days in the last 7 (missing data is not "no fire"; outages = no_data / not_operational, which are
             known on the day; 'partial' is not used because its rule looks at a centred window, i.e. the future).
             No season features: with one year, day-of-year is a time index and validation/test lie outside the
             training months (add them back with multi-year data).
  scored     cells with any NOAA-20 fire on or before t (cells that never burned are not scored: a known limit);
             issue dates whose label window contains a NOAA-20 outage day are left out (an outage is not a negative)
  blocks     weekly issue dates, train / validation / test, each separated by the horizon so no label window crosses
             a boundary; the test block is scored once, by `godseye evaluate` (ticket 11b), never during training
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from godseye.risk.panel import neighbour_sum

FEATURES = [
    "fire_days_7", "fire_days_14", "fire_days_30", "fire_days_90", "fire_freq_hist",
    "cells_7", "cells_30", "det_7", "det_30", "frp_sum_7", "frp_sum_30", "frp_mean_30", "night_share_30",
    "days_since_fire", "fire_streak", "accel_7_30", "nbr_fire_days_7", "nbr_fire_days_30",
    "cell_lat", "cell_lon", "gap_days_7",
]


class PanelV2:
    """Dense (cell x day) matrices of one reference sensor's 0.25° grid, plus that sensor's daily coverage gaps."""

    def __init__(self, grid: pd.DataFrame, gap_days: pd.Series, grid_deg: float, horizon: int):
        """grid: one sensor's rows of the sensor grid; gap_days: bool per date (True = outage, known on the day)."""
        self.grid_deg, self.horizon = grid_deg, horizon
        self.dates = pd.date_range(gap_days.index.min(), gap_days.index.max(), freq="D")
        self.gap = gap_days.reindex(self.dates, fill_value=True).to_numpy(np.float32)
        cells = grid[["cell_lat", "cell_lon"]].drop_duplicates().sort_values(["cell_lat", "cell_lon"])
        self.cells = cells.reset_index(drop=True)
        ci = pd.MultiIndex.from_frame(self.cells).get_indexer(pd.MultiIndex.from_frame(grid[["cell_lat", "cell_lon"]]))
        di = (pd.to_datetime(grid.acq_date) - self.dates[0]).dt.days.to_numpy()
        if len(di) and (di.min() < 0 or di.max() >= len(self.dates)):
            raise ValueError("grid dates fall outside the availability date range")
        shape = (len(self.cells), len(self.dates))

        def mat(values):
            m = np.zeros(shape, np.float32)
            m[ci, di] = values
            return m

        self.fire = mat(1.0)
        self.cells_m = mat(grid.n_fire_cells.to_numpy())
        night = grid.n_fire_cells.to_numpy() - grid.n_fire_cells_daytime.to_numpy()
        self.cs = {k: np.concatenate([np.zeros((shape[0], 1), np.float32), np.cumsum(m, axis=1, dtype=np.float32)], 1)
                   for k, m in {"fire": self.fire, "cells": self.cells_m, "det": mat(grid.n_detections.to_numpy()),
                                "frp": mat(grid.frp_sum_mw.to_numpy()), "night": mat(night)}.items()}
        self.gap_cs = np.concatenate([[0.0], np.cumsum(self.gap)])
        self.first_fire = np.where(self.fire.any(1), self.fire.argmax(1), len(self.dates))
        self.rows = np.floor((self.cells.cell_lat.to_numpy() + 90) / grid_deg).astype(int)
        self.cols = np.floor((self.cells.cell_lon.to_numpy() + 180) / grid_deg).astype(int)

    def window(self, key: str, t: int, w: int) -> np.ndarray:
        return self.cs[key][:, t + 1] - self.cs[key][:, max(0, t + 1 - w)]

    def features(self, t: int) -> pd.DataFrame:
        f = {f"fire_days_{w}": self.window("fire", t, w) for w in (7, 14, 30, 90)}
        f["fire_freq_hist"] = self.cs["fire"][:, t + 1] / (t + 1)
        for w in (7, 30):
            f[f"cells_{w}"], f[f"det_{w}"] = self.window("cells", t, w), self.window("det", t, w)
            f[f"frp_sum_{w}"] = self.window("frp", t, w)
        with np.errstate(divide="ignore", invalid="ignore"):
            f["frp_mean_30"] = np.where(f["det_30"] > 0, f["frp_sum_30"] / f["det_30"], 0.0)
            f["night_share_30"] = np.where(f["cells_30"] > 0, self.window("night", t, 30) / f["cells_30"], np.nan)
        past = self.fire[:, :t + 1][:, ::-1]                       # column 0 = day t
        burned = past.max(1) > 0
        f["days_since_fire"] = np.where(burned, past.argmax(1), 365).astype(np.float32)
        streak = np.where(past[:, 0] > 0, (past == 0).argmax(1), 0).astype(np.float32)
        streak[(past > 0).all(1)] = t + 1
        f["fire_streak"] = streak
        f["accel_7_30"] = f["fire_days_7"] / (f["fire_days_30"] * 7 / 30 + 1)
        f["nbr_fire_days_7"] = neighbour_sum(f["fire_days_7"], self.rows, self.cols, self.grid_deg)
        f["nbr_fire_days_30"] = neighbour_sum(f["fire_days_30"], self.rows, self.cols, self.grid_deg)
        f["cell_lat"], f["cell_lon"] = self.cells.cell_lat.to_numpy(), self.cells.cell_lon.to_numpy()
        f["gap_days_7"] = np.full(len(self.cells), self.gap_cs[t + 1] - self.gap_cs[max(0, t - 6)], np.float32)
        out = pd.DataFrame(f)[FEATURES].astype(np.float32)
        out["t"], out["cell_id"] = t, np.arange(len(self.cells))
        return out[self.first_fire <= t].reset_index(drop=True)

    def label(self, t: int, cell_id: np.ndarray) -> np.ndarray:
        """Any reference-sensor fire in t+1..t+horizon (requires t + horizon within the data)."""
        if t + self.horizon >= len(self.dates):
            raise ValueError("label window runs past the data")
        return (self.window("fire", t + self.horizon, self.horizon)[cell_id] > 0).astype(np.int8)

    def label_window_has_outage(self, t: int) -> bool:
        return bool(self.gap[t + 1:t + 1 + self.horizon].any())


@dataclass
class Blocks:
    train: list[int]          # day indices of issue dates
    validation: list[int]
    test: list[int]


def issue_blocks(dates: pd.DatetimeIndex, cfg: dict, horizon: int) -> Blocks:
    """Weekly issue dates anchored on the configured test end (so new data doesn't shift them), split by the
    configured dates (ADR 0005). Raises if any label window would cross a block boundary."""
    anchor = int(dates.get_loc(pd.Timestamp(cfg["test"][1])))
    step, first = cfg["step_days"], cfg["min_history_days"]
    issue = list(range(anchor, first - 1, -step))[::-1]
    day = lambda t: dates[t]
    b = Blocks([t for t in issue if day(t) <= pd.Timestamp(cfg["train_end"])],
               [t for t in issue if pd.Timestamp(cfg["validation"][0]) <= day(t) <= pd.Timestamp(cfg["validation"][1])],
               [t for t in issue if pd.Timestamp(cfg["test"][0]) <= day(t) <= pd.Timestamp(cfg["test"][1])])
    check_separation(b, horizon, len(dates))
    return b


def check_separation(b: Blocks, horizon: int, n_days: int) -> None:
    if not (b.train and b.validation and b.test):
        raise ValueError(f"empty block: train {len(b.train)}, validation {len(b.validation)}, test {len(b.test)}")
    if max(b.train) + horizon > min(b.validation):
        raise ValueError("a train label window overlaps the validation block")
    if max(b.validation) + horizon > min(b.test):
        raise ValueError("a validation label window overlaps the test block")
    if max(b.test) + horizon > n_days - 1:
        raise ValueError("a test label window runs past the data")


def build(panel: PanelV2, ts: list[int]) -> tuple[pd.DataFrame, np.ndarray]:
    ts = [t for t in ts if not panel.label_window_has_outage(t)]
    X = pd.concat([panel.features(t) for t in ts], ignore_index=True)
    y = np.concatenate([panel.label(t, X.cell_id[X.t == t].to_numpy()) for t in ts])
    return X, y
