"""
7-day wildfire risk model (v1 behaviour, unchanged).

Trains a gradient-boosted classifier for
    P(at least one fire detection in the cell during days t+1 .. t+7)
on weekly issue dates, holds out the last `val_weeks` issue dates, then refits on everything labelled.
"""
from __future__ import annotations

import time
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd

from godseye.clean.io import find_table
from godseye.config import get_config
from godseye.risk import artifact
from godseye.risk.metrics import evaluate
from godseye.risk.model import LGB_PARAMS, RISK_BINS, RISK_LABELS, predict_latest, risk_level
from godseye.risk.panel import FEATURES, HORIZON_DAYS, Panel, load_grid


def artifact_data_path() -> Path:
    return find_table(get_config().processed_dir, "fires_daily_grid")


def run(*, grid_path: Path | None, out: Path, predictions: Path, grid_deg: float, step: int, val_weeks: int,
        n_estimators: int, min_history_days: int) -> dict:
    t0 = time.time()
    grid = load_grid(grid_path)
    panel = Panel(grid, grid_deg)
    print(f"panel: {len(panel.cells):,} cells x {len(panel.dates)} days "
          f"({panel.dates[0].date()} -> {panel.dates[-1].date()})  [{time.time() - t0:.0f}s]")

    last_labelled = len(panel.dates) - 1 - HORIZON_DAYS
    issue = list(range(last_labelled, min_history_days - 1, -step))[::-1]
    val_issue = issue[-val_weeks:]
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
    model = lgb.train(LGB_PARAMS, dtrain, num_boost_round=n_estimators, valid_sets=[dvalid],
                      callbacks=[lgb.early_stopping(50, verbose=False)])
    best_iter = model.best_iteration or n_estimators
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
        "model": final, "features": FEATURES, "grid_deg": grid_deg, "horizon_days": HORIZON_DAYS,
        "risk_bins": RISK_BINS, "risk_labels": RISK_LABELS,
        "trained_through": str(panel.dates[-1].date()), "validation": metrics,
        "feature_importance_gain": dict(sorted(zip(FEATURES, (round(float(g), 1) for g in gain)),
                                               key=lambda kv: -kv[1])),
    }
    data_path = grid_path or artifact_data_path()
    artifact.save(bundle, out, {
        "name": Path(out).name, "version": Path(out).name, "params": LGB_PARAMS, "best_iteration": best_iter,
        "data_window": [str(panel.dates[0].date()), str(panel.dates[-1].date())],
        "data_sha256": artifact.file_sha256(data_path),
        "git_sha": artifact.git_sha(Path(__file__).resolve().parents[3]),
        "issue_dates": {"train": [str(panel.dates[train_issue[0]].date()), str(panel.dates[train_issue[-1]].date())],
                        "validation": [str(panel.dates[val_issue[0]].date()), str(panel.dates[val_issue[-1]].date())]},
    })

    preds = predict_latest(bundle, panel)
    preds.to_csv(predictions, index=False)
    print(f"\nsaved {out}  |  {len(preds):,} cell forecasts for {preds.issued.iat[0]} -> "
          f"{preds.valid_through.iat[0]} in {predictions}  [{time.time() - t0:.0f}s total]")
    print(preds.level.value_counts().reindex(RISK_LABELS).fillna(0).astype(int).to_string())
    return bundle
