"""
A fitted sensor link (source sensor -> target sensor's scale) and seam 2: harmonize(values, link) -> value + band.

fit_link() runs the whole protocol on paired data: cross-validate every candidate, choose by out-of-sample error,
refit the winner on all data, build the 90% band from its held-out errors, and record diagnostics (bootstrap CI of
the global ratio, monthly drift, band coverage). Only ratio-type winners can be applied (identity, global or
region-level ratios); a quantile-map winner is refused loudly rather than silently approximated.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from godseye.harmonize import validate as V

RATIO_METHODS = {"identity", "global_ratio", "region_month_shrunk_ratio"}


@dataclass
class Link:
    source: str
    target: str
    method: str
    coefficients: pd.DataFrame          # level (global | region | region_month), region, month, ratio
    band: pd.DataFrame                  # yhat_from, yhat_to, n, lo_factor, hi_factor
    provisional: bool
    report: dict = field(default_factory=dict)

    def ratios(self, region: np.ndarray | None = None, month: np.ndarray | None = None) -> np.ndarray | float:
        """Ratio per value: region x calendar month, else region, else global. month: 1-12 or 'YYYY-MM'."""
        c = self.coefficients
        if month is not None:
            month = np.asarray(month)
            if month.dtype.kind in "UO":
                month = pd.to_datetime(month).month.to_numpy()
        r_global = float(c.loc[c.level == "global", "ratio"].iloc[0])
        if region is None or set(c.level) == {"global"}:
            return r_global if region is None else np.full(len(region), r_global)
        reg = c[c.level == "region"].set_index("region").ratio
        rm = c[c.level == "region_month"].set_index(["region", "month"]).ratio
        r = rm.reindex(pd.MultiIndex.from_arrays([region, month])).to_numpy() if month is not None else \
            np.full(len(region), np.nan)
        r = np.where(np.isnan(r), reg.reindex(region).to_numpy(), r)
        return np.where(np.isnan(r), r_global, r)


def harmonize(x: np.ndarray, link: Link, region: np.ndarray | None = None,
              month: np.ndarray | None = None) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Seam 2: source-sensor values -> (value, lo, hi) on the target sensor's scale. NaN in, NaN out."""
    x = np.asarray(x, dtype=np.float64)
    value = x * link.ratios(region, month)
    lo, hi = V.apply_band(np.nan_to_num(value), link.band)
    return value, np.where(np.isnan(value), np.nan, lo), np.where(np.isnan(value), np.nan, hi)


def fit_link(df: pd.DataFrame, source: str, target: str, provisional: bool, region_deg: float | None = None) -> Link:
    cv = V.cross_validate(df)
    methods = [m for m in V.METHODS if m in cv]
    score = V.scores(cv, methods)
    chosen = V.choose(score)
    if chosen not in RATIO_METHODS:
        raise NotImplementedError(f"{chosen} won for {source}->{target}; only ratio methods can be applied")
    model = V.candidates(df)[chosen]
    coef = model.coefficients()
    band = V.band_table(cv[chosen].to_numpy(), cv.y.to_numpy())
    report = {
        "source": source, "target": target, "method": chosen, "provisional": provisional,
        "unit": "region x week totals of fire cell-days on days both sensors delivered full data",
        "region_deg": region_deg, "weeks": int(df.week.nunique()), "region_weeks": len(df),
        "first_week": str(df.week.min().date()), "last_week": str(df.week.max().date()),
        "folds": sorted(cv.fold.unique().tolist()), "cv_scores": score,
        "versus_global_ratio": V.versus_global_ratio(score, chosen),
        "global_ratio_bootstrap_90": V.bootstrap_global_ratio(df),
        "band": band.round(4).to_dict("records"),
        "band_coverage_out_of_fold": V.band_coverage(cv, chosen),
        "monthly_drift": V.drift(df),
        "shrinkage_k": getattr(model, "k", None),
    }
    report["caveats"] = caveats(report, df)
    return Link(source, target, chosen, coef, band, provisional, report)


DRIFT_FLAG = 0.03


def caveats(report: dict, df: pd.DataFrame) -> list[str]:
    """Plain-language warnings derived from the diagnostics, so they can't be forgotten in the write-up."""
    out = []
    overall = float(df.y.sum() / df.x.sum())
    for d in report["monthly_drift"]:
        if abs(d["ratio_y_over_x"] / overall - 1) > DRIFT_FLAG:
            out.append(f"{d['month']}: monthly ratio {d['ratio_y_over_x']:.3f} differs from the overall "
                       f"{overall:.3f} by more than {DRIFT_FLAG:.0%}")
    if abs(report["band_coverage_out_of_fold"] - 0.90) > 0.05:
        out.append(f"band coverage out of fold is {report['band_coverage_out_of_fold']:.1%}, not ~90%")
    if report["provisional"]:
        out.append("provisional: fitted on drifting-orbit years (ADR 0001)")
    if len(report["folds"]) < 6:
        out.append(f"only {len(report['folds'])} cross-validation folds")
    return out
