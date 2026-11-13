"""
Climatology, activity gate, anomalies and critical periods for one AOI's weekly series (ADR 0006).

Input: a year x ISO-week grid (53 columns) of values with coverage and data_days, e.g. the harmonized headline.

  usable week    coverage full, or partial with >= MIN_PARTIAL_DAYS days of data (scaled to 7 days); none, absent and
                 thinner partial weeks are left out, never read as zero
  history year   a year with >= MIN_YEAR_SHARE of its weeks usable
  climatology    per ISO week (week 53 pooled into 52), from usable values of history years in a +-POOL week window:
                 median, p10, p90, mean, std, and p_active = share of values that are "active"
  active week    activity="absolute" (ADR 0006 as approved): value >= ACTIVE (1 fire cell-day)
                 activity="relative" (PROPOSED amendment, awaiting sign-off): value >= max(ACTIVE, ACTIVE_SHARE x the
                 AOI's peak weekly median), so stray background detections in a large AOI don't make every week active
                 The threshold and gate use every history year (including one being tested for anomalies); only the
                 anomaly reference distribution is leave-one-year-out.
  gate (ADR 0006, fixed in advance)
                 history < MIN_YEARS          -> insufficient_history: no climatology-based panels
                 mean weekly value < FLOOR    -> floor: no critical periods ("too little detected activity")
                 weeks with p_active >= 10%   -> default, if at least 8 weeks pass
                 otherwise the top 20% weeks by p_active -> relative
  anomaly        a gated, usable week whose value is >= the p90, or z >= 2, of the climatology built WITHOUT its own
                 year (so a big year can't hide its own anomaly)
  critical period  a run of consecutive gated weeks (wrapping over New Year), ranked by expected (median) activity
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import numpy as np

WEEKS = 52
MIN_PARTIAL_DAYS = 5
MIN_YEAR_SHARE = 0.75
POOL = 1
ACTIVE = 1.0
ACTIVE_SHARE = 0.10
ACTIVITY_MODES = ("absolute", "relative")
MIN_YEARS = 5
FLOOR = 1.0
DEFAULT_P = 0.10
MIN_GATED_WEEKS = 8
RELATIVE_SHARE = 0.20
Z_ANOMALY = 2.0


@dataclass
class Analysis:
    years: list[int]
    history_years: list[int]
    status: Literal["ok", "insufficient_history"]
    message: str | None
    gate_rule: Literal["default", "relative", "floor"] | None
    gated_weeks: list[int]               # 1-based ISO weeks
    climatology: list[dict] = field(default_factory=list)
    anomalies: list[dict] = field(default_factory=list)
    critical_periods: list[dict] = field(default_factory=list)
    mean_weekly: float | None = None
    active_threshold: float | None = None
    activity: str = "absolute"
    gate_counts: dict = field(default_factory=dict)   # for the ingest report: weeks passing each rule


def usable(values: np.ndarray, coverage: np.ndarray, data_days: np.ndarray) -> np.ndarray:
    """Week values that can enter a climatology (NaN otherwise); thin partial weeks scaled to a full week."""
    v = np.asarray(values, dtype=np.float64)
    days = np.asarray(data_days, dtype=np.float64)
    full = coverage == "full"
    part = (coverage == "partial") & (days >= MIN_PARTIAL_DAYS)
    with np.errstate(invalid="ignore", divide="ignore"):
        scaled = np.where(part, v * 7.0 / days, v)
    return np.where(full | part, scaled, np.nan)[:, :WEEKS + 1]


def _fold53(u: np.ndarray) -> np.ndarray:
    """Pool ISO week 53 into week 52 (week 53 exists in few years)."""
    u = u.copy()
    w53 = u[:, 52]
    u[:, 51] = np.where(np.isnan(u[:, 51]), w53, np.where(np.isnan(w53), u[:, 51], (u[:, 51] + w53) / 2))
    return u[:, :WEEKS]


def _window(u: np.ndarray, w: int) -> np.ndarray:
    cols = [(w + k) % WEEKS for k in range(-POOL, POOL + 1)]
    x = u[:, cols].ravel()
    return x[~np.isnan(x)]


def _stats(x: np.ndarray, active: float = ACTIVE) -> dict:
    if not len(x):
        return {"median": None, "p10": None, "p90": None, "mean": None, "std": None, "p_active": None, "n": 0}
    return {"median": float(np.median(x)), "p10": float(np.quantile(x, 0.10)), "p90": float(np.quantile(x, 0.90)),
            "mean": float(x.mean()), "std": float(x.std(ddof=1)) if len(x) > 1 else 0.0,
            "p_active": float((x >= active).mean()), "n": int(len(x))}


def active_threshold(H: np.ndarray, activity: str = "absolute") -> float:
    if activity not in ACTIVITY_MODES:
        raise ValueError(f"activity must be one of {ACTIVITY_MODES}")
    if activity == "absolute":
        return ACTIVE
    peak = max((np.median(x) for w in range(WEEKS) if len(x := _window(H, w))), default=0.0)
    return max(ACTIVE, ACTIVE_SHARE * float(peak))


def percentile_of(value: float, reference: np.ndarray) -> float | None:
    """Share of reference values at or below `value` (mid-rank for ties), 0-100."""
    ref = np.asarray(reference, dtype=np.float64)
    ref = ref[~np.isnan(ref)]
    if not len(ref) or np.isnan(value):
        return None
    return float(100 * ((ref < value).sum() + 0.5 * (ref == value).sum()) / len(ref))


def week_reference(years: list[int], values: np.ndarray, coverage: np.ndarray, data_days: np.ndarray, week: int,
                   exclude_year: int | None = None) -> np.ndarray:
    """Usable values of ISO week `week` (pooled +-POOL) in every year except `exclude_year`: the "same week in past
    years" reference used by "this week vs history" (ticket 10)."""
    u = _fold53(usable(values, coverage, data_days))
    keep = np.array([y != exclude_year for y in years])
    return _window(u[keep], min(week, WEEKS) - 1)


def gate(clim: list[dict], mean_weekly: float) -> tuple[str, list[int], dict]:
    """(rule, gated ISO weeks, counts for every rule). Weeks without a climatology never pass."""
    p = np.array([c["p_active"] if c["p_active"] is not None else np.nan for c in clim])
    med = np.array([c["median"] if c["median"] is not None else 0.0 for c in clim])
    passed = np.flatnonzero(np.nan_to_num(p, nan=-1) >= DEFAULT_P)
    k = int(np.ceil(RELATIVE_SHARE * WEEKS))
    order = np.lexsort((-med, -np.nan_to_num(p, nan=-1)))           # by p_active, then median, both descending
    relative = [int(i) for i in order[:k] if np.nan_to_num(p[i]) > 0]
    counts = {"default_rule_weeks": int(len(passed)), "relative_rule_weeks": len(relative),
              "mean_weekly": round(float(mean_weekly), 3), "floor": FLOOR, "min_gated_weeks": MIN_GATED_WEEKS}
    if mean_weekly < FLOOR:
        return "floor", [], counts
    if len(passed) >= MIN_GATED_WEEKS:
        return "default", [int(i) + 1 for i in passed], counts
    return "relative", sorted(i + 1 for i in relative), counts


def critical_periods(clim: list[dict], gated: list[int]) -> list[dict]:
    """Runs of consecutive gated weeks (circular), ranked by summed median activity."""
    if not gated:
        return []
    on = np.zeros(WEEKS, bool)
    on[np.array(gated) - 1] = True
    if on.all():
        runs = [list(range(WEEKS))]
    else:
        start = int(np.flatnonzero(~on)[0])                     # begin scanning at a gap so runs don't split
        runs, cur = [], []
        for k in range(1, WEEKS + 1):
            w = (start + k) % WEEKS
            if on[w]:
                cur.append(w)
            elif cur:
                runs.append(cur)
                cur = []
        if cur:
            runs.append(cur)
    med = np.array([c["median"] or 0.0 for c in clim])
    total = med.sum() or 1.0
    out = [{"start_week": r[0] + 1, "end_week": r[-1] + 1, "weeks": len(r),
            "peak_week": int(r[int(np.argmax(med[r]))]) + 1, "expected_activity": round(float(med[r].sum()), 2),
            "share_of_year": round(float(med[r].sum() / total), 3),
            "mean_p_active": round(float(np.mean([clim[w]["p_active"] or 0 for w in r])), 3)} for r in runs]
    out.sort(key=lambda d: -d["expected_activity"])
    for i, d in enumerate(out, 1):
        d["rank"] = i
    return out


def analyse(years: list[int], values: np.ndarray, coverage: np.ndarray, data_days: np.ndarray,
            activity: str = "absolute") -> Analysis:
    u = _fold53(usable(values, coverage, data_days))
    share = (~np.isnan(u)).mean(axis=1)
    hist = share >= MIN_YEAR_SHARE
    history_years = [y for y, h in zip(years, hist) if h]
    if len(history_years) < MIN_YEARS:
        return Analysis(years, history_years, "insufficient_history",
                        f"needs ≥{MIN_YEARS} years of history (currently {len(history_years)})", None, [])
    H = u[hist]
    active = active_threshold(H, activity)
    rounded = lambda d: {k: (round(v, 3) if isinstance(v, float) else v) for k, v in d.items()}
    clim = [{"week": w + 1, **rounded(_stats(_window(H, w), active))} for w in range(WEEKS)]
    mean_weekly = float(np.nanmean(u))              # ADR 0006 rule 3: over the whole record, not only history years
    rule, gated, counts = gate(clim, mean_weekly)
    message = "too little detected activity to define critical periods" if rule == "floor" else None

    anomalies = []
    for i, y in enumerate(history_years):
        others = np.delete(H, i, axis=0)                 # leave-one-year-out reference
        if rule == "floor":                              # ADR 0006: no season, so compare with the whole record
            whole = _stats(others[~np.isnan(others)])
            ref = dict.fromkeys(range(WEEKS), whole)
            weeks = range(WEEKS)
        else:
            weeks = [w - 1 for w in gated]
            ref = {w: _stats(_window(others, w)) for w in weeks}
        for w in weeks:
            v, r = H[i, w], ref[w]
            if np.isnan(v) or r["n"] < 3:
                continue
            if v < active:                               # an anomaly must at least be activity
                continue
            z = (v - r["mean"]) / r["std"] if r["std"] else None
            if (v >= r["p90"] and v > r["median"]) or (z is not None and z >= Z_ANOMALY):
                anomalies.append({"year": y, "week": w + 1, "value": round(float(v), 2),
                                  "median": round(r["median"], 2), "p90": round(r["p90"], 2),
                                  "z": round(float(z), 2) if z is not None else None})
    anomalies.sort(key=lambda a: -(a["z"] if a["z"] is not None else 0))
    periods = [] if rule == "floor" else critical_periods(clim, gated)
    return Analysis(years, history_years, "ok", message, rule, gated, clim, anomalies, periods, round(mean_weekly, 3),
                    round(active, 3), activity, counts)
