"""
Burning activity calendar: per-sensor daily series for an AOI, folded into a year x period grid.

Values come from the pre-aggregated 0.25° sensor grid, so a request never scans detections. An AOI is the set of
0.25° cells whose centre lies inside its bbox. Sensors are never summed. Every period carries a coverage flag:
  full     every day in the period has data (status ok)
  partial  some days are missing or only partially delivered: the value counts the days with data and
           data_days says how many there were; it is never presented as a complete period
  none     no day has data: the value is null, never zero
  absent   the period does not exist that year (ISO week 53 of a 52-week year, day 366 of a non-leap year)
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from godseye.ingest.aggregate import STATUSES

METRICS = {"cell_days": "n_fire_cells", "detections": "n_detections"}
OK, PARTIAL, GAP = 0, 1, 2


def lon_in(lon: np.ndarray, west: float, east: float) -> np.ndarray:
    """Longitudes inside [west, east]; west > east means the box crosses the antimeridian."""
    return (lon >= west) & (lon <= east) if west <= east else (lon >= west) | (lon <= east)


def in_bbox(lat, lon, bbox: tuple[float, float, float, float]):
    """Works on numpy arrays and pandas Series alike."""
    west, south, east, north = bbox
    return (lat >= south) & (lat <= north) & lon_in(lon, west, east)


def grid_cells(bbox: tuple[float, float, float, float], deg: float) -> tuple[int, list[float] | None]:
    """How many grid cells have their centre inside bbox, and the bbox snapped to those cells' edges."""
    h = deg / 2
    lats = np.arange(-90 + h, 90, deg).round(4)
    lons = np.arange(-180 + h, 180, deg).round(4)
    west, south, east, north = bbox
    lat_c = lats[(lats >= south) & (lats <= north)]
    lon_c = lons[lon_in(lons, west, east)]
    if not len(lat_c) or not len(lon_c):
        return 0, None
    if west <= east:
        snapped_w, snapped_e = lon_c.min(), lon_c.max()
    else:  # antimeridian: the box runs from its western block (>= west) round to its eastern block (<= east)
        western, eastern = lon_c[lon_c >= west], lon_c[lon_c <= east]
        snapped_w = western.min() if len(western) else eastern.min()
        snapped_e = eastern.max() if len(eastern) else western.max()
    return len(lat_c) * len(lon_c), [round(float(v), 4) for v in (snapped_w - h, lat_c.min() - h,
                                                                     snapped_e + h, lat_c.max() + h)]


def _codes(values: pd.Series, categories: list[str]) -> np.ndarray:
    """Integer codes of values in `categories`; cheap when the column is already categorical in that order."""
    if isinstance(values.dtype, pd.CategoricalDtype) and list(values.cat.categories) == categories:
        return values.cat.codes.to_numpy(np.int64)
    return pd.Categorical(values.astype(str), categories=categories).codes.astype(np.int64)


@dataclass
class Calendar:
    years: list[int]
    periods: int
    values: np.ndarray     # (sensors, years, periods), NaN where coverage is none or absent
    coverage: np.ndarray   # (sensors, years, periods) of "full" | "partial" | "none" | "absent"
    data_days: np.ndarray  # (sensors, years, periods) days in the period with data
    period_days: int       # 7 for weeks, 1 for days


class CalendarStore:
    """The 0.25° sensor grid and the sensor availability table, held in memory."""

    def __init__(self, grid: pd.DataFrame, avail: pd.DataFrame, grid_deg: float):
        self.sensors = list(avail.sensor.cat.categories)
        self.grid_deg = grid_deg
        self.first = pd.Timestamp(avail.acq_date.min())
        self.last = pd.Timestamp(avail.acq_date.max())
        self.dates = pd.date_range(self.first, self.last, freq="D")
        n_days = len(self.dates)

        self.code = _codes(grid.sensor, self.sensors)
        self.day = (grid.acq_date.to_numpy().astype("datetime64[D]")
                    - np.datetime64(self.first.date(), "D")).astype(np.int64)
        self.lat, self.lon = grid.cell_lat.to_numpy(), grid.cell_lon.to_numpy()
        self.metrics = {k: grid[col].to_numpy(np.float64) for k, col in METRICS.items()}

        status = np.full((len(self.sensors), n_days), GAP, np.int8)
        a_code = _codes(avail.sensor, self.sensors)
        a_day = (avail.acq_date.to_numpy().astype("datetime64[D]")
                 - np.datetime64(self.first.date(), "D")).astype(np.int64)
        a_status = _codes(avail.status, STATUSES)
        status[a_code, a_day] = np.select([a_status == STATUSES.index("ok"), a_status == STATUSES.index("partial")],
                                          [OK, PARTIAL], GAP)
        self.status = status

    def daily(self, bbox: tuple[float, float, float, float], metric: str) -> np.ndarray:
        """(sensors, days) sum of the metric over the AOI's cells; NaN on coverage-gap days."""
        m = in_bbox(self.lat, self.lon, bbox)
        n_s, n_d = len(self.sensors), len(self.dates)
        out = np.bincount(self.code[m] * n_d + self.day[m], weights=self.metrics[metric][m],
                          minlength=n_s * n_d).reshape(n_s, n_d)
        return np.where(self.status == GAP, np.nan, out)

    def calendar(self, bbox: tuple[float, float, float, float], metric: str, unit: str) -> Calendar:
        return fold(self.daily(bbox, metric), self.status, self.dates, unit)


def fold(daily: np.ndarray, status: np.ndarray, dates: pd.DatetimeIndex, unit: str) -> Calendar:
    """Daily (sensors, days) -> year x period grid. Weeks are ISO weeks (1..53); days are day of year (1..366)."""
    if unit == "week":
        iso = dates.isocalendar()
        year, period, length = iso.year.to_numpy(np.int64), iso.week.to_numpy(np.int64) - 1, 7
        periods = 53
    elif unit == "day":
        year, period, length = dates.year.to_numpy(np.int64), dates.dayofyear.to_numpy(np.int64) - 1, 1
        periods = 366
    else:
        raise ValueError(f"unit must be 'week' or 'day', not {unit!r}")
    years = list(range(int(year.min()), int(year.max()) + 1))
    slot = (year - years[0]) * periods + period
    n_slots = len(years) * periods
    exists = np.ones((len(years), periods), bool)
    for i, y in enumerate(years):
        if unit == "week" and pd.Timestamp(y, 12, 28).isocalendar().week < 53:   # Dec 28 is always in the last week
            exists[i, 52] = False
        if unit == "day" and not pd.Timestamp(y, 1, 1).is_leap_year:
            exists[i, 365] = False

    values, coverage, days = [], [], []
    for s in range(daily.shape[0]):
        has_data = status[s] != GAP
        total = np.bincount(slot[has_data], weights=daily[s, has_data], minlength=n_slots).reshape(exists.shape)
        data_days = np.bincount(slot[has_data], minlength=n_slots).reshape(exists.shape)
        ok_days = np.bincount(slot[status[s] == OK], minlength=n_slots).reshape(exists.shape)
        cov = np.where(data_days == 0, "none", np.where(ok_days == length, "full", "partial"))
        cov = np.where(exists, cov, "absent")
        values.append(np.where((data_days == 0) | ~exists, np.nan, total))
        coverage.append(cov)
        days.append(data_days)
    return Calendar(years, periods, np.array(values), np.array(coverage), np.array(days), length)
