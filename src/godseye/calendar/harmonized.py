"""
The calendar's harmonized headline series (ADR 0001): one Aqua-equivalent value per day, never a sum of sensors.

  up to `observed_until` (2021): Aqua-MODIS observed, on days Aqua delivered data
  otherwise (and from 2022, when Aqua's orbit drifts): an estimate from VIIRS. Each day takes the first sensor in
    `priority` that delivered full data (else the first with partial data), converted to reference units with its
    continuity link, then mapped to the target with the headline link. Ratios are applied per grid cell (its region
    and calendar month) before summing over the AOI, so regional links stay correct.

Band (90%, weekly totals only; the links are calibrated on weekly totals): observed days are exact; the estimated part
gets the headline link's band, widened in log space by the continuity band of the substitute sensors in proportion to
their share of days (conservative: a relative error on a share s of the total contributes s, not s^2). Day view gets
no band.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from godseye.calendar.store import GAP, OK, PARTIAL, fold
from godseye.harmonize.link import Link
from godseye.harmonize.series import region_of
from godseye.harmonize.validate import apply_band


@dataclass
class Chain:
    target: str
    label: str
    reference: str
    priority: list[str]                  # reference first
    continuity: dict[str, Link | None]   # sensor -> link onto the reference (None for the reference itself)
    headline: Link                       # reference -> target
    region_deg: float
    observed_until: pd.Timestamp | None = None   # target observed is the headline up to this day


def build_chain(headline_cfg: dict, links: list[Link], region_deg: float) -> Chain | None:
    by_pair = {(k.source, k.target): k for k in links}
    ref, target = headline_cfg["reference"], headline_cfg["target"]
    if (ref, target) not in by_pair:
        return None
    if headline_cfg["viirs_priority"][0] != ref:
        raise ValueError(f"viirs_priority must start with the reference sensor {ref}")
    continuity = {s: (None if s == ref else by_pair.get((s, ref))) for s in headline_cfg["viirs_priority"]}
    priority = [s for s in headline_cfg["viirs_priority"] if s == ref or continuity[s] is not None]
    until = headline_cfg.get("observed_until")
    return Chain(target, headline_cfg["label"], ref, priority, continuity, by_pair[(ref, target)], region_deg,
                 pd.Timestamp(until) if until else None)


def row_ratios(link: Link | None, lat: np.ndarray, lon: np.ndarray, month: np.ndarray, region_deg: float) -> np.ndarray:
    """Ratio of `link` for every grid row, computed once per distinct (region, month)."""
    if link is None:
        return np.ones(len(lat))
    if set(link.coefficients.level) == {"global"}:
        return np.full(len(lat), float(link.ratios()))
    assert region_deg >= 0.5, "region keys below assume fewer than 500 regions per hemisphere axis"
    rlat = np.floor(lat / region_deg).astype(np.int64) + 500          # offsets keep every part non-negative
    rlon = np.floor(lon / region_deg).astype(np.int64) + 500
    key = (rlat * 1000 + rlon) * 100 + month
    uniq, inverse = np.unique(key, return_inverse=True)
    u_month = uniq % 100
    u_lat = ((uniq // 100) // 1000 - 500) * region_deg + region_deg / 2
    u_lon = ((uniq // 100) % 1000 - 500) * region_deg + region_deg / 2
    regions = region_of(u_lat, u_lon, region_deg)
    return np.asarray(link.ratios(regions, u_month), dtype=np.float64)[inverse]


@dataclass
class HarmonizedCalendar:
    values: np.ndarray            # (years, periods) target-equivalent values, NaN where coverage is none or absent
    lo: np.ndarray                # NaN in day view (bands are calibrated on weekly totals)
    hi: np.ndarray
    coverage: np.ndarray
    data_days: np.ndarray
    estimated_days: np.ndarray    # days whose value is an estimate from VIIRS (the rest are target observed)
    substituted_days: np.ndarray  # estimated days supplied by a sensor other than the reference
    years: list[int]              # row labels, as fold() produces them


@dataclass
class Daily:
    value: np.ndarray       # headline value per day, NaN = no source
    ref_value: np.ndarray   # the estimated part in reference units (0 on observed days), for the continuity band
    status: np.ndarray      # status of the source used (GAP = none)
    estimated: np.ndarray   # 1.0 where the value is a VIIRS estimate
    substituted: np.ndarray  # 1.0 where the estimate came from a substitute sensor


class HarmonizedSeries:
    """Per-row weights for the chain, precomputed once for the calendar store's grid rows."""

    def __init__(self, chain: Chain, store):
        self.chain = chain
        sensors = store.sensors
        self.idx = [sensors.index(s) for s in chain.priority]
        self.target_idx = sensors.index(chain.target)
        month = store.dates.month.to_numpy()[store.day]
        cell_days = store.metrics["cell_days"]
        self.rows, self.ref_units, self.target_units = [], [], []
        for s in self.idx:
            m = store.code == s
            lat, lon = store.lat[m], store.lon[m]
            ref = cell_days[m] * row_ratios(chain.continuity[sensors[s]], lat, lon, month[m], chain.region_deg)
            self.rows.append(np.flatnonzero(m))
            self.ref_units.append(ref)
            self.target_units.append(ref * row_ratios(chain.headline, lat, lon, month[m], chain.region_deg))
        self.obs_rows = np.flatnonzero(store.code == self.target_idx)
        self.obs_units = cell_days[self.obs_rows]

    def daily(self, inside: np.ndarray, day: np.ndarray, dates: pd.DatetimeIndex, status: np.ndarray) -> Daily:
        n_days, n = len(dates), len(self.idx)
        target, ref = np.zeros((n, n_days)), np.zeros((n, n_days))
        for i, rows in enumerate(self.rows):
            keep = inside[rows]
            d = day[rows][keep]
            target[i] = np.bincount(d, weights=self.target_units[i][keep], minlength=n_days)
            ref[i] = np.bincount(d, weights=self.ref_units[i][keep], minlength=n_days)
        st = status[self.idx]                                   # (n, days)
        choice = np.where((st == OK).any(0), (st == OK).argmax(0),
                          np.where((st == PARTIAL).any(0), (st == PARTIAL).argmax(0), -1))
        cols = np.arange(n_days)
        has = choice >= 0
        pick = np.where(has, choice, 0)
        value = np.where(has, target[pick, cols], np.nan)
        ref_value = np.where(has, ref[pick, cols], 0.0)
        src_status = np.where(has, st[pick, cols], GAP)
        estimated = has.astype(np.float64)
        substituted = (has & (pick != 0)).astype(np.float64)    # priority[0] is the reference (build_chain checks)

        if self.chain.observed_until is not None:
            keep = inside[self.obs_rows]
            obs = np.bincount(day[self.obs_rows][keep], weights=self.obs_units[keep], minlength=n_days)
            obs_status = status[self.target_idx]
            use = (dates <= self.chain.observed_until) & (obs_status != GAP)
            value = np.where(use, obs, value)
            src_status = np.where(use, obs_status, src_status)
            ref_value = np.where(use, 0.0, ref_value)
            estimated = np.where(use, 0.0, estimated)
            substituted = np.where(use, 0.0, substituted)
        return Daily(value, ref_value, src_status, estimated, substituted)

    def calendar(self, inside: np.ndarray, day: np.ndarray, dates: pd.DatetimeIndex, status: np.ndarray,
                 unit: str) -> HarmonizedCalendar:
        d = self.daily(inside, day, dates, status)
        st = d.status[None]
        total = fold(d.value[None], st, dates, unit)
        est = fold((np.nan_to_num(d.value) * d.estimated)[None], st, dates, unit).values[0]
        ref_est = fold(d.ref_value[None], st, dates, unit).values[0]
        est_days = np.nan_to_num(fold(d.estimated[None], st, dates, unit).values[0])
        sub_days = np.nan_to_num(fold(d.substituted[None], st, dates, unit).values[0])
        v = total.values[0]
        nan = np.isnan(v)
        if unit == "week":
            e = np.nan_to_num(est)
            lo_e, hi_e = apply_band(e, self.chain.headline.band)
            lo_e, hi_e = self._widen(e, lo_e, hi_e, np.nan_to_num(ref_est), sub_days, est_days)
            observed = np.nan_to_num(v) - e
            lo = np.where(nan, np.nan, observed + np.where(est_days > 0, lo_e, 0.0))
            hi = np.where(nan, np.nan, observed + np.where(est_days > 0, hi_e, 0.0))
        else:
            lo = hi = np.full_like(v, np.nan)
        return HarmonizedCalendar(v, lo, hi, total.coverage[0], total.data_days[0], est_days.astype(int),
                                  sub_days.astype(int), total.years)

    def _widen(self, v, lo, hi, ref_v, sub_days, est_days):
        """Widen the estimate's band where substitute sensors supplied days (log space, weighted by their share).
        Uses the widest substitute band and looks it up at the period's reference-unit total (conservative)."""
        subs = [k for k in (self.chain.continuity[s] for s in self.chain.priority[1:]) if k is not None]
        if not subs or not sub_days.sum():
            return lo, hi
        band = max(subs, key=lambda k: float(k.band.hi_factor.iloc[1:].max())).band
        with np.errstate(divide="ignore", invalid="ignore"):
            share = np.where(est_days > 0, sub_days / est_days, 0.0)
            f_lo, f_hi = apply_band(ref_v, band)
            l2 = np.where(ref_v > 0, np.log(np.maximum(f_lo, 1e-9) / ref_v), 0.0)       # <= 0
            h2 = np.where(ref_v > 0, np.log(f_hi / ref_v), 0.0)                         # >= 0
            l1 = np.where((v > 0) & (lo > 0), np.log(lo / v), -np.inf)
            h1 = np.where(v > 0, np.log(hi / v), 0.0)
            new_lo = np.where(np.isfinite(l1), v * np.exp(-np.sqrt(l1 ** 2 + share * l2 ** 2)), lo)
            new_hi = np.where(v > 0, v * np.exp(np.sqrt(h1 ** 2 + share * h2 ** 2)), hi)
        return new_lo, new_hi
