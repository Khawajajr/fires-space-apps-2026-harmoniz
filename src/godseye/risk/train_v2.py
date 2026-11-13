"""`godseye train-v2`: train risk model v2 from scratch (ADRs 0004, 0005). The test block is not touched here."""
from __future__ import annotations

import time
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd

from godseye.clean.io import find_table, read_table
from godseye.config import Config
from godseye.risk import artifact
from godseye.risk.evaluate import scores
from godseye.risk.model import LGB_PARAMS
from godseye.risk.v2 import FEATURES, PanelV2, build, issue_blocks

COLUMNS = ["sensor", "acq_date", "cell_lat", "cell_lon", "n_detections", "n_fire_cells", "n_fire_cells_daytime",
           "frp_sum_mw"]


def load_panel(cfg: Config, processed: Path) -> PanelV2:
    v2 = cfg.risk_v2
    grid = read_table(processed, "sensor_grid_daily", COLUMNS)
    grid = grid[grid.sensor.astype(str) == v2["reference_sensor"]]
    avail = read_table(processed, "sensor_availability")
    a = avail[avail.sensor.astype(str) == v2["reference_sensor"]]
    # Outages only (no_data / not_operational), which are known on the day; 'partial' uses a centred window.
    gap = pd.Series(a.status.astype(str).isin(["no_data", "not_operational"]).to_numpy(),
                    index=pd.to_datetime(a.acq_date))
    return PanelV2(grid, gap, cfg.clean["grid_deg"], cfg.risk["horizon_days"])


def run(cfg: Config, processed: Path, out: Path, n_estimators: int) -> dict:
    t0 = time.time()
    v2 = cfg.risk_v2
    panel = load_panel(cfg, processed)
    blocks = issue_blocks(panel.dates, v2, panel.horizon)
    span = lambda ts: [str(panel.dates[ts[0]].date()), str(panel.dates[ts[-1]].date())]
    Xtr, ytr = build(panel, blocks.train)
    Xva, yva = build(panel, blocks.validation)
    print(f"panel: {len(panel.cells):,} cells x {len(panel.dates)} days; train {len(Xtr):,} rows "
          f"{span(blocks.train)} positive {ytr.mean():.3f}; validation {len(Xva):,} rows {span(blocks.validation)} "
          f"positive {yva.mean():.3f}; test {span(blocks.test)} held out  [{time.time() - t0:.0f}s]")

    model = lgb.train(LGB_PARAMS, lgb.Dataset(Xtr[FEATURES], ytr), num_boost_round=n_estimators,
                      valid_sets=[lgb.Dataset(Xva[FEATURES], yva)], callbacks=[lgb.early_stopping(50, verbose=False)])
    best = model.best_iteration or n_estimators
    model = lgb.train(LGB_PARAMS, lgb.Dataset(Xtr[FEATURES], ytr), num_boost_round=best)   # train block only, no refit
    pva = model.predict(Xva[FEATURES])
    validation = [scores(yva, pva, "LightGBM v2"),
                  scores(yva, (Xva.fire_days_7 > 0).astype(float).to_numpy(), "persistence (any fire in last 7 days)"),
                  scores(yva, 1 - (1 - Xva.fire_freq_hist.to_numpy()) ** 7, "2026 frequency to date")]
    gain = model.feature_importance(importance_type="gain")
    bundle = {"model": model, "features": FEATURES, "grid_deg": panel.grid_deg, "horizon_days": panel.horizon,
              "risk_bins": cfg.risk["risk_bins"], "risk_labels": cfg.risk["risk_labels"],
              "trained_through": span(blocks.train)[1], "validation": validation,
              "feature_importance_gain": dict(sorted(zip(FEATURES, (round(float(g), 1) for g in gain)),
                                                     key=lambda kv: -kv[1]))}
    artifact.save(bundle, out, {
        "name": out.name, "version": "v2", "params": LGB_PARAMS, "best_iteration": best,
        "label": f"any {v2['reference_sensor']} fire cell-day in the 0.25 deg cell in days t+1..t+{panel.horizon}",
        "reference_sensor": v2["reference_sensor"],
        "blocks": {"train": span(blocks.train), "validation": span(blocks.validation), "test": span(blocks.test)},
        "n_issue_dates": {"train": len(blocks.train), "validation": len(blocks.validation), "test": len(blocks.test)},
        "data_window": [str(panel.dates[0].date()), str(panel.dates[-1].date())],
        "data_sha256": artifact.file_sha256(find_table(processed, "sensor_grid_daily")),
        "git_sha": artifact.git_sha(cfg.root), "test_scored": False,
        "note": "Validation metrics only; the test block is scored once by `godseye evaluate` (ticket 11b).",
    })
    print(pd.DataFrame(validation).to_string(index=False))
    print(f"best_iteration {best}; saved {out}  [{time.time() - t0:.0f}s]")
    return {"validation": validation, "best_iteration": best, "positive_rate_train": float(np.mean(ytr))}
