"""Probability calibration and reliability tables (numpy only, ADR 0002)."""
from __future__ import annotations

import numpy as np


def isotonic_fit(p: np.ndarray, y: np.ndarray, n_bins: int = 200) -> tuple[list[float], list[float]]:
    """Pool-adjacent-violators on `n_bins` quantile bins of p: a monotone map p -> observed rate.
    Returns breakpoints (x, y) for np.interp."""
    order = np.argsort(p, kind="stable")
    p, y = np.asarray(p, float)[order], np.asarray(y, float)[order]
    edges = np.unique(np.quantile(p, np.linspace(0, 1, n_bins + 1)))
    idx = np.clip(np.searchsorted(edges, p, "right") - 1, 0, len(edges) - 2)
    w = np.bincount(idx, minlength=len(edges) - 1).astype(float)
    keep = w > 0
    xs = (np.bincount(idx, weights=p, minlength=len(w))[keep] / w[keep])
    ys = (np.bincount(idx, weights=y, minlength=len(w))[keep] / w[keep])
    w = w[keep]
    # PAV
    vals, wts, xs_out = list(ys), list(w), [[x] for x in xs]
    i = 0
    while i < len(vals) - 1:
        if vals[i] > vals[i + 1]:
            tot = wts[i] + wts[i + 1]
            vals[i] = (vals[i] * wts[i] + vals[i + 1] * wts[i + 1]) / tot
            wts[i] = tot
            xs_out[i] += xs_out.pop(i + 1)
            vals.pop(i + 1)
            wts.pop(i + 1)
            i = max(i - 1, 0)
        else:
            i += 1
    x_mid = [float(np.mean(x)) for x in xs_out]
    return x_mid, [float(v) for v in vals]


def isotonic_apply(p: np.ndarray, breakpoints: tuple[list[float], list[float]]) -> np.ndarray:
    x, y = breakpoints
    return np.interp(np.asarray(p, float), x, y)


def reliability(y: np.ndarray, p: np.ndarray, n_bins: int = 10) -> list[dict]:
    """Observed rate vs mean prediction in equal-width probability bins."""
    y, p = np.asarray(y, float), np.asarray(p, float)
    b = np.clip((p * n_bins).astype(int), 0, n_bins - 1)
    out = []
    for k in range(n_bins):
        m = b == k
        if m.any():
            out.append({"bin": f"{k / n_bins:.1f}-{(k + 1) / n_bins:.1f}", "n": int(m.sum()),
                        "mean_predicted": round(float(p[m].mean()), 4), "observed_rate": round(float(y[m].mean()), 4)})
    return out
