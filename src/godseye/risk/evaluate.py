"""Seam 4: predictions + labels in, metrics out (numpy only, ADR 0002)."""
from __future__ import annotations

import numpy as np

from godseye.risk.metrics import average_precision, roc_auc


def brier(y: np.ndarray, p: np.ndarray) -> float:
    return float(np.mean((np.clip(np.asarray(p, float), 0, 1) - np.asarray(y, float)) ** 2))


def brier_skill(y: np.ndarray, p: np.ndarray, p_ref: np.ndarray) -> float | None:
    """1 - Brier(model) / Brier(reference): > 0 means better than the reference forecast."""
    ref = brier(y, p_ref)
    return None if ref == 0 else 1 - brier(y, p) / ref


def scores(y, p, name: str, refs: dict[str, np.ndarray] | None = None) -> dict:
    y = np.asarray(y).astype(int)
    p = np.asarray(p, dtype=float)
    two_classes = 0 < y.sum() < len(y)
    out = {"model": name, "n": int(len(y)), "positive_rate": round(float(y.mean()), 4),
           "roc_auc": round(float(roc_auc(y, p)), 4) if two_classes else None,
           "pr_auc": round(average_precision(y, p), 4) if y.sum() else None,
           "brier": round(brier(y, p), 4)}
    for ref_name, p_ref in (refs or {}).items():
        b = brier_skill(y, p, p_ref)
        out[f"bss_vs_{ref_name}"] = round(b, 4) if b is not None else None
    return out
