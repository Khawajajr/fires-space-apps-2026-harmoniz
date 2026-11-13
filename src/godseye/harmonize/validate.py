"""
Out-of-sample comparison of the candidate mappings, the uncertainty band, and the selection rule.

  folds       leave one calendar month (of weeks) out; with several years, leave one year out instead
  metrics     on held-out predictions: WAPE (sum |error| / sum y; used instead of MAPE, which is undefined for
              the many zero weeks), MAPE on region-months with y >= 50, MAE and correlation, for region x month
              values, region x week values, and the global weekly and monthly series
  selection   the simplest method (order: identity, global ratio, shrunk ratio, quantile map) whose region-month
              WAPE is within SELECTION_TOLERANCE (relative) of the best: a more complex method must beat the
              simpler ones out of sample by more than noise (a one-standard-error-style rule)
  band        90% predictive band from held-out errors (used instead of a pure bootstrap band, which only
              captures coefficient uncertainty): multiplicative 5th/95th percentiles of y / y_hat per bin of
              y_hat, plus an additive upper bound for y_hat = 0 (an observed zero can hide fire the other sensor
              saw). Coverage is checked on folds the band was not built from; the residuals themselves come from
              models that saw those folds' neighbours, so the check is slightly optimistic
  bootstrap   resampling whole folds (months, or years when there are several) gives a 90% interval for the
              global ratio; whole folds keep the time dependence between neighbouring weeks
  caveat      the winner is chosen on the same held-out scores it reports, so its score is slightly optimistic
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from godseye.harmonize.methods import GlobalRatio, Identity, QuantileMap, ShrunkRatio

K_GRID = [10.0, 30.0, 100.0, 300.0, 1000.0]
BAND_EDGES = [0.0, 5.0, 20.0, 100.0, 500.0, np.inf]   # bins of predicted weekly value (y_hat)


def fold_key(df: pd.DataFrame) -> pd.Series:
    years = df.month.str[:4]
    return years if years.nunique() >= 3 else df.month


def wape(y: np.ndarray, yhat: np.ndarray) -> float:
    return float(np.abs(y - yhat).sum() / max(y.sum(), 1e-9))


def _pick_k(train: pd.DataFrame) -> float:
    """Shrinkage strength by inner leave-one-fold-out on the training data only."""
    keys = fold_key(train)
    scores = {}
    for k in K_GRID:
        err = tot = 0.0
        for f in keys.unique():
            inner, held = train[keys != f], train[keys == f]
            yhat = ShrunkRatio(k).fit(inner).predict(held)
            err += np.abs(held.y.to_numpy() - yhat).sum()
            tot += held.y.sum()
        scores[k] = err / max(tot, 1e-9)
    return min(scores, key=scores.get)


def candidates(train: pd.DataFrame) -> dict:
    return {"identity": Identity().fit(train),
            "global_ratio": GlobalRatio().fit(train),
            "region_month_shrunk_ratio": ShrunkRatio(_pick_k(train)).fit(train),
            "quantile_map_region_season": QuantileMap().fit(train)}


def cross_validate(df: pd.DataFrame) -> pd.DataFrame:
    """Held-out predictions of every candidate: df plus one column per method."""
    keys = fold_key(df)
    out = []
    for f in sorted(keys.unique()):
        train, held = df[keys != f], df[keys == f].copy()
        for name, model in candidates(train).items():
            held[name] = model.predict(held)
        held["fold"] = f
        out.append(held)
    return pd.concat(out, ignore_index=True)


def _corr(a, b) -> float | None:
    return round(float(np.corrcoef(a, b)[0, 1]), 4) if len(a) > 2 and np.std(a) > 0 and np.std(b) > 0 else None


def scores(cv: pd.DataFrame, methods: list[str]) -> dict:
    rm = cv.groupby(["region", "month"])[["y", "x", *methods]].sum()
    wk = cv.groupby("week")[["y", *methods]].sum()
    mo = cv.groupby("month")[["y", *methods]].sum()
    big = rm[rm.y >= 50]
    out = {}
    for m in methods:
        mape = round(float((np.abs(big.y - big[m]) / big.y).mean()), 4) if len(big) else None
        out[m] = {"region_month_wape": round(wape(rm.y.to_numpy(), rm[m].to_numpy()), 4),
                  "region_month_mape_y50": mape,
                  "region_month_mae": round(float(np.abs(rm.y - rm[m]).mean()), 3),
                  "region_month_corr": _corr(rm.y, rm[m]),
                  "region_week_wape": round(wape(cv.y.to_numpy(), cv[m].to_numpy()), 4),
                  "region_week_corr": _corr(cv.y, cv[m]),
                  "weekly_global_wape": round(wape(wk.y.to_numpy(), wk[m].to_numpy()), 4),
                  "weekly_global_corr": _corr(wk.y, wk[m]),
                  "monthly_global_wape": round(wape(mo.y.to_numpy(), mo[m].to_numpy()), 4),
                  "monthly_global_corr": _corr(mo.y, mo[m])}
    return out


METHODS = ["identity", "global_ratio", "region_month_shrunk_ratio", "quantile_map_region_season"]  # simplest first
SELECTION_TOLERANCE = 0.02


def choose(score: dict) -> str:
    scored = [m for m in METHODS if m in score]
    best = min(score[m]["region_month_wape"] for m in scored)
    return next(m for m in scored if score[m]["region_month_wape"] <= best * (1 + SELECTION_TOLERANCE))


def versus_global_ratio(score: dict, chosen: str) -> str:
    """Plain statement of how the chosen method compares with the global-ratio baseline (Phase 3 acceptance)."""
    if chosen == "global_ratio":
        return "the chosen method is the global-ratio baseline itself"
    a, b = score[chosen]["region_month_wape"], score["global_ratio"]["region_month_wape"]
    change = (a - b) / b
    if a < b * (1 - SELECTION_TOLERANCE):
        return f"beats the global ratio out of sample: region-month WAPE {a} vs {b} ({change:+.1%})"
    if a <= b * (1 + SELECTION_TOLERANCE):
        return (f"ties the global ratio within the {SELECTION_TOLERANCE:.0%} noise tolerance ({a} vs {b}, "
                f"{change:+.1%}); shipped because it is simpler")
    return f"does NOT beat the global ratio ({a} vs {b}, {change:+.1%})"


def band_table(yhat: np.ndarray, y: np.ndarray, level: float = 0.90) -> pd.DataFrame:
    """
    Band per bin of y_hat: value * [lo_factor, hi_factor], and for y_hat = 0 (first row) [0, hi_add]: when the
    source sensor saw nothing, the target may still have seen something.
    """
    lo_q, hi_q = (1 - level) / 2, 1 - (1 - level) / 2
    zero = y[yhat == 0]
    rows = [{"yhat_from": 0.0, "yhat_to": 0.0, "n": int(len(zero)), "lo_factor": 0.0, "hi_factor": 0.0,
             "hi_add": float(np.quantile(zero, hi_q)) if len(zero) else 0.0}]
    pos = yhat > 0
    yp, ratio = yhat[pos], y[pos] / yhat[pos]
    for lo, hi in zip(BAND_EDGES[:-1], BAND_EDGES[1:]):
        r = ratio[(yp > lo) & (yp <= hi)]
        if len(r) >= 20:
            rows.append({"yhat_from": lo, "yhat_to": hi, "n": int(len(r)), "lo_factor": float(np.quantile(r, lo_q)),
                         "hi_factor": float(np.quantile(r, hi_q)), "hi_add": 0.0})
    if len(rows) == 1 and len(ratio):     # too little data for bins: one band for every positive value
        rows.append({"yhat_from": 0.0, "yhat_to": np.inf, "n": int(len(ratio)), "hi_add": 0.0,
                     "lo_factor": float(np.quantile(ratio, lo_q)), "hi_factor": float(np.quantile(ratio, hi_q))})
    t = pd.DataFrame(rows)
    # Bigger predicted totals are steadier: never let a bigger bin get a wider band than the one before it.
    t.loc[1:, "lo_factor"] = t.lo_factor[1:].cummax()
    t.loc[1:, "hi_factor"] = t.hi_factor[1:].cummin()
    return t


def apply_band(yhat: np.ndarray, table: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    pos = table.iloc[1:]
    i = np.clip(np.searchsorted(pos.yhat_from.to_numpy(), yhat, "left") - 1, 0, len(pos) - 1)
    lo = np.where(yhat > 0, yhat * pos.lo_factor.to_numpy()[i], 0.0)
    hi = np.where(yhat > 0, yhat * pos.hi_factor.to_numpy()[i], table.hi_add.iloc[0])
    return lo, hi


def band_coverage(cv: pd.DataFrame, method: str) -> float:
    """Share of held-out values (zero predictions included) inside a band built without their own fold."""
    hits = n = 0
    for f in cv.fold.unique():
        rest, held = cv[cv.fold != f], cv[cv.fold == f]
        lo, hi = apply_band(held[method].to_numpy(), band_table(rest[method].to_numpy(), rest.y.to_numpy()))
        y = held.y.to_numpy()
        hits += int(((y >= lo - 1e-9) & (y <= hi + 1e-9)).sum())
        n += len(y)
    return round(hits / max(n, 1), 4)


def bootstrap_global_ratio(df: pd.DataFrame, n: int = 500, seed: int = 0) -> list[float]:
    """5th, 50th, 95th percentile of the global ratio, resampling whole folds (months, or years)."""
    rng = np.random.default_rng(seed)
    units = df.groupby(fold_key(df))[["x", "y"]].sum()
    idx = rng.integers(0, len(units), size=(n, len(units)))
    r = units.y.to_numpy()[idx].sum(1) / units.x.to_numpy()[idx].sum(1)
    return [round(float(v), 4) for v in np.quantile(r, [0.05, 0.5, 0.95])]


def drift(df: pd.DataFrame) -> list[dict]:
    """Monthly y / x of the paired totals: a change over time is drift, not noise."""
    m = df.groupby("month")[["x", "y"]].sum()
    return [{"month": k, "ratio_y_over_x": round(float(r.y / r.x), 4), "x": int(r.x), "y": int(r.y)}
            for k, r in m.iterrows()]
