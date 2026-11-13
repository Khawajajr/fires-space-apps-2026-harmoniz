"""Classification metrics in numpy/pandas (no sklearn / scipy: see ADR 0002)."""
from __future__ import annotations

import numpy as np
import pandas as pd


def roc_auc(y, p):
    """Mann-Whitney U formulation with average ranks for ties."""
    ranks = pd.Series(p).rank().to_numpy()
    pos = y == 1
    n_pos, n_neg = pos.sum(), (~pos).sum()
    return (ranks[pos].sum() - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg)


def average_precision(y, p):
    order = np.argsort(-p, kind="stable")
    y, p = y[order], p[order]
    tp = np.cumsum(y)
    last_of_tie = np.r_[p[1:] != p[:-1], True]   # score thresholds, ties grouped
    precision = tp[last_of_tie] / (np.flatnonzero(last_of_tie) + 1)
    recall_gain = np.diff(np.r_[0, tp[last_of_tie]]) / tp[-1]
    return float((precision * recall_gain).sum())


def evaluate(y, p, name):
    y = np.asarray(y).astype(int)
    p = np.asarray(p, dtype=float)
    return {"model": name, "roc_auc": round(roc_auc(y, p), 4), "pr_auc": round(average_precision(y, p), 4),
            "brier": round(float(np.mean((np.clip(p, 0, 1) - y) ** 2)), 4)}
