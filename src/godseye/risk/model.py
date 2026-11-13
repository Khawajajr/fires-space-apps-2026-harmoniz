"""Risk levels and scoring the latest day with a trained model bundle."""
from __future__ import annotations

import pickle
from pathlib import Path

import numpy as np
import pandas as pd

from godseye.config import get_config
from godseye.risk.panel import HORIZON_DAYS, Panel

RISK_BINS = get_config().risk["risk_bins"]
RISK_LABELS = get_config().risk["risk_labels"]

# Native LightGBM API on purpose: the scikit-learn wrapper pulls in scipy.stats, whose DLLs
# have been blocked by Windows Smart App Control on the dev machine (ADR 0002).
LGB_PARAMS = {"objective": "binary", "learning_rate": 0.05, "num_leaves": 63, "min_data_in_leaf": 200,
              "bagging_fraction": 0.8, "bagging_freq": 1, "feature_fraction": 0.8, "lambda_l2": 1.0,
              "metric": "average_precision", "verbosity": -1}


def risk_level(p: np.ndarray) -> np.ndarray:
    return np.asarray(RISK_LABELS, dtype=object)[np.digitize(p, RISK_BINS)]


def load_bundle(path: Path) -> dict:
    with open(path, "rb") as fh:
        return pickle.load(fh)


def predict_latest(bundle: dict, panel: Panel) -> pd.DataFrame:
    """Risk for days (last_date+1 .. last_date+7) for every cell with fire history."""
    t = len(panel.dates) - 1
    feats = panel.features(t)
    p = bundle["model"].predict(feats[bundle["features"]])
    issued = panel.dates[t]
    return pd.DataFrame({
        "cell_lat": feats.cell_lat, "cell_lon": feats.cell_lon,
        "risk": p.round(4), "level": risk_level(p),
        "issued": issued.strftime("%Y-%m-%d"),
        "valid_through": (issued + pd.Timedelta(days=HORIZON_DAYS)).strftime("%Y-%m-%d"),
    })
