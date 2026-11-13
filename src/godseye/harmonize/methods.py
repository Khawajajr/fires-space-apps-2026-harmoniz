"""
Candidate mappings from sensor x to reference sensor y, fitted on paired region x week totals.

  Identity        y ~ x: no correction (the simplest candidate; wins when the sensors already agree)
  GlobalRatio     y ~ r * x with one ratio for everything
  ShrunkRatio     a ratio per region and per region x calendar month, each shrunk towards its parent
                  (region -> global, region x month -> region) with prior strength k, in units of x
                  (a gamma-Poisson / empirical-Bayes style estimate: (sum y + k r_parent) / (sum x + k))
  QuantileMap     per region x season, maps x's quantile in its own distribution to the same quantile of y's;
                  falls back to season-wide, then global, distributions when a key has fewer than `min_n` weeks

All are numpy/pandas only (ADR 0002).
"""
from __future__ import annotations

import numpy as np
import pandas as pd


class Identity:
    name = "identity"

    def fit(self, df: pd.DataFrame) -> Identity:
        return self

    def predict(self, df: pd.DataFrame) -> np.ndarray:
        return df.x.to_numpy(np.float64)

    def coefficients(self) -> pd.DataFrame:
        return pd.DataFrame({"level": ["global"], "region": ["*"], "month": [0], "ratio": [1.0]})


class GlobalRatio:
    name = "global_ratio"

    def fit(self, df: pd.DataFrame) -> GlobalRatio:
        self.ratio = float(df.y.sum() / df.x.sum())
        return self

    def predict(self, df: pd.DataFrame) -> np.ndarray:
        return self.ratio * df.x.to_numpy(np.float64)

    def coefficients(self) -> pd.DataFrame:
        return pd.DataFrame({"level": ["global"], "region": ["*"], "month": [0], "ratio": [self.ratio]})


class ShrunkRatio:
    name = "region_month_shrunk_ratio"

    def __init__(self, k: float):
        self.k = k

    def fit(self, df: pd.DataFrame) -> ShrunkRatio:
        k = self.k
        self.r_global = float(df.y.sum() / df.x.sum())
        reg = df.groupby("region")[["x", "y"]].sum()
        self.r_region = (reg.y + k * self.r_global) / (reg.x + k)
        cal_month = pd.to_datetime(df.month).dt.month
        rm = df.assign(cal_month=cal_month).groupby(["region", "cal_month"])[["x", "y"]].sum()
        parent = self.r_region.reindex(rm.index.get_level_values("region")).to_numpy()
        self.r_region_month = (rm.y + k * parent) / (rm.x + k)
        return self

    def ratios(self, df: pd.DataFrame) -> np.ndarray:
        cal_month = pd.to_datetime(df.month).dt.month.to_numpy()
        key = pd.MultiIndex.from_arrays([df.region.to_numpy(), cal_month])
        r = self.r_region_month.reindex(key).to_numpy()
        r = np.where(np.isnan(r), self.r_region.reindex(df.region).to_numpy(), r)
        return np.where(np.isnan(r), self.r_global, r)

    def predict(self, df: pd.DataFrame) -> np.ndarray:
        return self.ratios(df) * df.x.to_numpy(np.float64)

    def coefficients(self) -> pd.DataFrame:
        rm = self.r_region_month.rename("ratio").reset_index().rename(columns={"cal_month": "month"})
        return pd.concat([
            pd.DataFrame({"level": ["global"], "region": ["*"], "month": [0], "ratio": [self.r_global]}),
            pd.DataFrame({"level": "region", "region": self.r_region.index, "month": 0,
                          "ratio": self.r_region.to_numpy()}),
            rm.assign(level="region_month")[["level", "region", "month", "ratio"]],
        ], ignore_index=True)


def _quantile_map(x: np.ndarray, xs: np.ndarray, ys: np.ndarray) -> np.ndarray:
    """Mid-rank of x in sorted xs -> the same quantile of sorted ys (linear interpolation)."""
    n = len(xs)
    rank = (np.searchsorted(xs, x, "left") + np.searchsorted(xs, x, "right")) / 2
    p = np.clip(rank / n, 0, 1)
    return np.interp(p, (np.arange(n) + 0.5) / n, ys)


class QuantileMap:
    name = "quantile_map_region_season"

    def __init__(self, min_n: int = 8):
        self.min_n = min_n

    def fit(self, df: pd.DataFrame) -> QuantileMap:
        sort = lambda g: (np.sort(g.x.to_numpy(np.float64)), np.sort(g.y.to_numpy(np.float64)))
        self.global_ = sort(df)
        self.by_season = {s: sort(g) for s, g in df.groupby("season") if len(g) >= self.min_n}
        self.by_key = {k: sort(g) for k, g in df.groupby(["region", "season"]) if len(g) >= self.min_n}
        return self

    def predict(self, df: pd.DataFrame) -> np.ndarray:
        out = np.empty(len(df))
        for (region, season), idx in df.groupby(["region", "season"]).indices.items():
            xs, ys = self.by_key.get((region, season)) or self.by_season.get(season) or self.global_
            out[idx] = _quantile_map(df.x.to_numpy(np.float64)[idx], xs, ys)
        return out

    def coefficients(self) -> pd.DataFrame:
        """Equivalent mean ratio per key (sum of mapped / sum of x), for reporting; the mapping itself is not linear."""
        rows = [("global", "*", "*", self.global_)] + [("season", "*", s, v) for s, v in self.by_season.items()] + \
               [("region_season", r, s, v) for (r, s), v in self.by_key.items()]
        return pd.DataFrame([{"level": lv, "region": r, "season": s, "n_weeks": len(xs),
                              "ratio": float(ys.sum() / xs.sum()) if xs.sum() else np.nan}
                             for lv, r, s, (xs, ys) in rows])
