"""
God's Eye - 7-day wildfire risk model.

Turns the harmonized `fires_daily_grid` (cell x day aggregates from clean_fire_data.py)
into a dense cell x day panel, engineers per-cell spatio-temporal features as of an
"issue date" t, and trains a gradient-boosted classifier for:

    P(at least one fire detection in the cell during days t+1 .. t+7)

The probability is bucketed into risk levels (low .. extreme) for the map.

Feature groups (all computed only from data on or before t - no leakage):
  history     fire-day counts over 7/14/30/90 days, long-run fire frequency, detection counts
  intensity   rolling FRP sum / mean / max
  diurnal     night-detection ratio (night burning = drier fuels, persistent fires)
  dry-spell   PROXIES ONLY - there is no weather data in FIRMS: days since last fire,
              current consecutive burning streak, 7d-vs-30d acceleration, and mean background
              11 um brightness temperature (MODIS T31 / VIIRS I5) of detections, a surface heat proxy.
              Swap in real precipitation / VPD (GPM IMERG, ERA5) when available.
  spatial     fire days in the 8 neighbouring cells, cell lat/lon
  seasonal    sin/cos day-of-year of the issue date

Usage:
  python train_model.py [--grid ../data/processed/fires_daily_grid.parquet]
                        [--out ../models/gods_eye_risk_model.pkl] [--step 7] [--val-weeks 6]
"""
from __future__ import annotations

import argparse
import json
import pickle
import time
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
HORIZON_DAYS = 7
MIN_HISTORY_DAYS = 30
RISK_BINS = [0.10, 0.30, 0.50, 0.70]
RISK_LABELS = ["low", "moderate", "high", "very_high", "extreme"]
FEATURES = [
    "fire_days_7", "fire_days_14", "fire_days_30", "fire_days_90", "fire_freq_hist",
    "det_7", "det_30", "frp_sum_7", "frp_sum_30", "frp_mean_30", "frp_max_30",
    "night_ratio_30", "days_since_fire", "fire_streak", "accel_7_30", "bt31_mean_7",
    "nbr_fire_days_7", "nbr_fire_days_30", "cell_lat", "cell_lon", "doy_sin", "doy_cos",
]


def load_grid(path: Path | None = None) -> pd.DataFrame:
    if path is None:
        base = ROOT / "data" / "processed" / "fires_daily_grid"
        path = next(p for p in (base.with_suffix(s) for s in (".parquet", ".feather", ".csv.gz")) if p.exists())
    readers = {".parquet": pd.read_parquet, ".feather": pd.read_feather}
    grid = readers.get(path.suffix, pd.read_csv)(path)
    grid["acq_date"] = pd.to_datetime(grid["acq_date"])
    return grid


class Panel:
    """Dense (cell x day) matrices built from the sparse daily grid."""

    def __init__(self, grid: pd.DataFrame, grid_deg: float):
        self.grid_deg = grid_deg
        self.dates = pd.date_range(grid.acq_date.min(), grid.acq_date.max(), freq="D")
        cells = grid[["cell_lat", "cell_lon"]].drop_duplicates().sort_values(["cell_lat", "cell_lon"])
        self.cells = cells.reset_index(drop=True)
        cell_idx = pd.MultiIndex.from_frame(self.cells).get_indexer(
            pd.MultiIndex.from_frame(grid[["cell_lat", "cell_lon"]]))
        day_idx = (grid.acq_date - self.dates[0]).dt.days.to_numpy()
        shape = (len(self.cells), len(self.dates))

        def mat(values, fill=0.0):
            m = np.full(shape, fill, dtype=np.float32)
            m[cell_idx, day_idx] = values
            return m

        self.fire = mat(1.0)
        self.det = mat(grid.n_detections.to_numpy())
        self.frp_sum = mat(grid.frp_sum_mw.to_numpy())
        self.frp_max = mat(grid.frp_max_mw.to_numpy())
        self.night = mat(grid.n_night.to_numpy())
        bt31 = mat(grid.bt31_mean_k.to_numpy(), fill=np.nan)
        self.bt31_sum, self.bt31_n = np.nan_to_num(bt31), (~np.isnan(bt31)).astype(np.float32)
        # Cumulative sums with a leading zero column: window (t-w, t] = cs[:, t+1] - cs[:, t+1-w].
        self.cs = {k: np.concatenate([np.zeros((shape[0], 1), np.float32),
                                      np.cumsum(getattr(self, k), axis=1, dtype=np.float32)], axis=1)
                   for k in ("fire", "det", "frp_sum", "night", "bt31_sum", "bt31_n")}
        self.first_fire = self.fire.argmax(axis=1)
        self.rows = np.floor((self.cells.cell_lat.to_numpy() + 90) / grid_deg).astype(int)
        self.cols = np.floor((self.cells.cell_lon.to_numpy() + 180) / grid_deg).astype(int)

    def window(self, key: str, t: int, w: int) -> np.ndarray:
        return self.cs[key][:, t + 1] - self.cs[key][:, max(0, t + 1 - w)]

    def neighbours(self, values: np.ndarray) -> np.ndarray:
        """Sum of `values` over the 8 surrounding grid cells (self excluded)."""
        h, w = int(round(180 / self.grid_deg)), int(round(360 / self.grid_deg))
        g = np.zeros((h + 2, w + 2), np.float32)
        g[self.rows + 1, self.cols + 1] = values
        total = sum(g[1 + dr:h + 1 + dr, 1 + dc:w + 1 + dc]
                    for dr in (-1, 0, 1) for dc in (-1, 0, 1) if (dr, dc) != (0, 0))
        return total[self.rows, self.cols]

    def features(self, t: int) -> pd.DataFrame:
        """Feature table for every cell that has burned on or before day index t."""
        f = {}
        for w in (7, 14, 30, 90):
            f[f"fire_days_{w}"] = self.window("fire", t, w)
        f["fire_freq_hist"] = self.cs["fire"][:, t + 1] / (t + 1)
        f["det_7"], f["det_30"] = self.window("det", t, 7), self.window("det", t, 30)
        f["frp_sum_7"], f["frp_sum_30"] = self.window("frp_sum", t, 7), self.window("frp_sum", t, 30)
        with np.errstate(divide="ignore", invalid="ignore"):
            f["frp_mean_30"] = np.where(f["det_30"] > 0, f["frp_sum_30"] / f["det_30"], 0)
            f["night_ratio_30"] = np.where(f["det_30"] > 0, self.window("night", t, 30) / f["det_30"], np.nan)
            bt_n = self.window("bt31_n", t, 7)
            f["bt31_mean_7"] = np.where(bt_n > 0, self.window("bt31_sum", t, 7) / bt_n, np.nan)
        f["frp_max_30"] = self.frp_max[:, max(0, t - 29):t + 1].max(axis=1)

        past = self.fire[:, :t + 1][:, ::-1]           # column 0 = day t
        burned = past.max(axis=1) > 0
        f["days_since_fire"] = np.where(burned, past.argmax(axis=1), 365).astype(np.float32)
        f["fire_streak"] = np.where(past[:, 0] > 0, (past == 0).argmax(axis=1), 0).astype(np.float32)
        f["fire_streak"][(past > 0).all(axis=1)] = t + 1
        f["accel_7_30"] = f["fire_days_7"] / (f["fire_days_30"] * 7 / 30 + 1)

        f["nbr_fire_days_7"] = self.neighbours(f["fire_days_7"])
        f["nbr_fire_days_30"] = self.neighbours(f["fire_days_30"])
        f["cell_lat"], f["cell_lon"] = self.cells.cell_lat.to_numpy(), self.cells.cell_lon.to_numpy()
        doy = self.dates[t].dayofyear
        f["doy_sin"] = np.full(len(self.cells), np.sin(2 * np.pi * doy / 365.25), np.float32)
        f["doy_cos"] = np.full(len(self.cells), np.cos(2 * np.pi * doy / 365.25), np.float32)

        out = pd.DataFrame(f)[FEATURES].astype(np.float32)
        out["t"] = t
        out["cell_id"] = np.arange(len(self.cells))
        return out[self.first_fire <= t].reset_index(drop=True)

    def label(self, t: int, cell_id: np.ndarray) -> np.ndarray:
        return (self.window("fire", t + HORIZON_DAYS, HORIZON_DAYS)[cell_id] > 0).astype(np.int8)


def risk_level(p: np.ndarray) -> np.ndarray:
    return np.asarray(RISK_LABELS, dtype=object)[np.digitize(p, RISK_BINS)]


# Native LightGBM API on purpose: the scikit-learn wrapper pulls in scipy.stats, whose DLLs
# are blocked by Windows Smart App Control on the dev machine.
LGB_PARAMS = {"objective": "binary", "learning_rate": 0.05, "num_leaves": 63, "min_data_in_leaf": 200,
              "bagging_fraction": 0.8, "bagging_freq": 1, "feature_fraction": 0.8, "lambda_l2": 1.0,
              "metric": "average_precision", "verbosity": -1}


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


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--grid", type=Path)
    ap.add_argument("--out", type=Path, default=ROOT / "models" / "gods_eye_risk_model.pkl")
    ap.add_argument("--predictions", type=Path, default=ROOT / "data" / "processed" / "risk_predictions.csv")
    ap.add_argument("--grid-deg", type=float, default=0.25)
    ap.add_argument("--step", type=int, default=7, help="days between training issue dates")
    ap.add_argument("--val-weeks", type=int, default=6, help="most recent issue dates held out")
    ap.add_argument("--n-estimators", type=int, default=600)
    args = ap.parse_args()

    t0 = time.time()
    grid = load_grid(args.grid)
    panel = Panel(grid, args.grid_deg)
    print(f"panel: {len(panel.cells):,} cells x {len(panel.dates)} days "
          f"({panel.dates[0].date()} -> {panel.dates[-1].date()})  [{time.time() - t0:.0f}s]")

    last_labelled = len(panel.dates) - 1 - HORIZON_DAYS
    issue = list(range(last_labelled, MIN_HISTORY_DAYS - 1, -args.step))[::-1]
    val_issue = issue[-args.val_weeks:]
    # Train label windows must end before the first validation issue date (no overlap).
    train_issue = [t for t in issue if t + HORIZON_DAYS <= val_issue[0]]

    def build(ts):
        X = pd.concat([panel.features(t) for t in ts], ignore_index=True)
        y = np.concatenate([panel.label(t, X.cell_id[X.t == t].to_numpy()) for t in ts])
        return X, y

    Xtr, ytr = build(train_issue)
    Xva, yva = build(val_issue)
    d = lambda ts: f"{panel.dates[ts[0]].date()} -> {panel.dates[ts[-1]].date()}"
    print(f"train: {len(Xtr):,} rows, {len(train_issue)} issue dates {d(train_issue)}, positive rate {ytr.mean():.3f}")
    print(f"valid: {len(Xva):,} rows, {len(val_issue)} issue dates {d(val_issue)}, positive rate {yva.mean():.3f}")

    dtrain = lgb.Dataset(Xtr[FEATURES], ytr, free_raw_data=False)
    dvalid = lgb.Dataset(Xva[FEATURES], yva, reference=dtrain)
    model = lgb.train(LGB_PARAMS, dtrain, num_boost_round=args.n_estimators, valid_sets=[dvalid],
                      callbacks=[lgb.early_stopping(50, verbose=False)])
    best_iter = model.best_iteration or args.n_estimators
    pva = model.predict(Xva[FEATURES], num_iteration=best_iter)

    metrics = [
        evaluate(yva, pva, "LightGBM"),
        evaluate(yva, (Xva.fire_days_7 > 0).astype(float).to_numpy(), "baseline: burned in last 7 days"),
        evaluate(yva, Xva.fire_freq_hist.to_numpy(), "baseline: historical fire frequency"),
    ]
    print(f"\nvalidation (held-out last {len(val_issue)} weeks), best_iter={best_iter}")
    print(pd.DataFrame(metrics).to_string(index=False))
    lv = pd.crosstab(risk_level(pva), yva, normalize="index").reindex(RISK_LABELS)
    counts = pd.Series(risk_level(pva)).value_counts().reindex(RISK_LABELS).fillna(0).astype(int)
    print("\nobserved fire rate by predicted level (validation):")
    print(pd.DataFrame({"cells": counts, "fire_rate": lv.get(1, pd.Series(dtype=float)).round(3)}).to_string())

    # Refit on everything labelled, at the early-stopped size, for the shipped artifact.
    Xall, yall = pd.concat([Xtr, Xva], ignore_index=True), np.concatenate([ytr, yva])
    final = lgb.train(LGB_PARAMS, lgb.Dataset(Xall[FEATURES], yall), num_boost_round=best_iter)
    gain = final.feature_importance(importance_type="gain")
    bundle = {
        "model": final, "features": FEATURES, "grid_deg": args.grid_deg, "horizon_days": HORIZON_DAYS,
        "risk_bins": RISK_BINS, "risk_labels": RISK_LABELS,
        "trained_through": str(panel.dates[-1].date()), "validation": metrics,
        "feature_importance_gain": dict(sorted(zip(FEATURES, (round(float(g), 1) for g in gain)),
                                               key=lambda kv: -kv[1])),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "wb") as fh:
        pickle.dump(bundle, fh)
    (args.out.with_suffix(".json")).write_text(json.dumps({k: v for k, v in bundle.items() if k != "model"}, indent=2))

    preds = predict_latest(bundle, panel)
    pred_path = args.predictions
    preds.to_csv(pred_path, index=False)
    print(f"\nsaved {args.out}  |  {len(preds):,} cell forecasts for {preds.issued.iat[0]} -> "
          f"{preds.valid_through.iat[0]} in {pred_path}  [{time.time() - t0:.0f}s total]")
    print(preds.level.value_counts().reindex(RISK_LABELS).fillna(0).astype(int).to_string())


if __name__ == "__main__":
    main()
