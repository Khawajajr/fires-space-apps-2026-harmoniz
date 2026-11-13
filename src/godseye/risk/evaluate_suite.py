"""
`godseye evaluate`: score risk v2 once on the untouched test block and write every number of the model card.

Pre-declared choices (made before looking at test scores):
  calibration   isotonic regression fitted on the validation block; the served probabilities are calibrated
  baselines     persistence as a probability (P(label | fire in the last 7 days) and P(label | none), from the train
                block) and "2026 frequency to date" (1 - (1 - share of past days with fire)^7)
  subsets       new activity = no NOAA-20 fire in the cell in the 30 days before the issue date; regions by bbox
  spatial check 5-fold cross-validation over 5° blocks inside the train block, with and without cell lat/lon
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import lightgbm as lgb
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from godseye.config import Config  # noqa: E402
from godseye.risk import artifact  # noqa: E402
from godseye.risk.calibration import isotonic_apply, isotonic_fit, reliability  # noqa: E402
from godseye.risk.evaluate import scores  # noqa: E402
from godseye.risk.model import LGB_PARAMS  # noqa: E402
from godseye.risk.train_v2 import load_panel  # noqa: E402
from godseye.risk.v2 import build, issue_blocks  # noqa: E402

REGIONS = {   # first match wins; broad boxes, for a per-region breakdown only
    "Levant": (34.0, 29.0, 42.5, 37.5), "Argentina": (-74.0, -55.5, -53.5, -21.5),
    "South America (other)": (-92.0, -56.0, -30.0, 15.0), "North America": (-170.0, 15.0, -50.0, 75.0),
    "Europe": (-25.0, 35.0, 45.0, 72.0), "Africa": (-20.0, -36.0, 55.0, 35.0),
    "Asia": (45.0, -11.0, 180.0, 80.0), "Australia & Oceania": (110.0, -50.0, 180.0, -10.0),
}
SPATIAL_DEG, SPATIAL_FOLDS = 5.0, 5


def region_of(lat: np.ndarray, lon: np.ndarray) -> np.ndarray:
    out = np.full(len(lat), "Other", dtype=object)
    for name, (w, s, e, n) in reversed(REGIONS.items()):
        out[(lat >= s) & (lat <= n) & (lon >= w) & (lon <= e)] = name
    return out


def spatial_blocks(X: pd.DataFrame, y: np.ndarray, features: list[str], rounds: int) -> dict:
    """Train on 4/5 of the 5° blocks, score the held-out blocks; pooled over the folds (train block only)."""
    block = (np.floor(X.cell_lat / SPATIAL_DEG) * 1000 + np.floor(X.cell_lon / SPATIAL_DEG)).astype(int)
    fold = np.abs(pd.util.hash_array(block.to_numpy())) % SPATIAL_FOLDS
    pred = np.zeros(len(y))
    for f in range(SPATIAL_FOLDS):
        tr, te = fold != f, fold == f
        m = lgb.train(LGB_PARAMS, lgb.Dataset(X.loc[tr, features], y[tr]), num_boost_round=rounds)
        pred[te] = m.predict(X.loc[te, features])
    return scores(y, pred, f"spatial 5° blocks, {len(features)} features")


def run(cfg: Config, processed: Path, model_dir: Path, reports: Path, figures: Path, card: Path) -> dict:
    t0 = time.time()
    bundle = artifact.load(model_dir)
    model, feats = bundle["model"], bundle["features"]
    panel = load_panel(cfg, processed)
    blocks = issue_blocks(panel.dates, cfg.risk_v2, panel.horizon)
    (Xtr, ytr), (Xva, yva), (Xte, yte) = (build(panel, b) for b in (blocks.train, blocks.validation, blocks.test))
    span = lambda ts: [str(panel.dates[ts[0]].date()), str(panel.dates[ts[-1]].date())]

    pva, pte = model.predict(Xva[feats]), model.predict(Xte[feats])
    cal = isotonic_fit(pva, yva)                                       # validation only
    pte_cal = isotonic_apply(pte, cal)
    p1, p0 = float(ytr[Xtr.fire_days_7 > 0].mean()), float(ytr[Xtr.fire_days_7 == 0].mean())
    persist = lambda X: np.where(X.fire_days_7 > 0, p1, p0)
    freq = lambda X: 1 - (1 - X.fire_freq_hist.to_numpy()) ** panel.horizon
    refs = lambda X: {"persistence": persist(X), "frequency_to_date": freq(X)}

    test = [scores(yte, pte_cal, "LightGBM v2 (calibrated)", refs(Xte)),
            scores(yte, pte, "LightGBM v2 (raw)", refs(Xte)),
            scores(yte, persist(Xte), "persistence (any fire in last 7 days)", refs(Xte)),
            scores(yte, freq(Xte), "2026 frequency to date", refs(Xte))]
    new = (Xte.fire_days_30 == 0).to_numpy()
    new_refs = {k: v[new] for k, v in refs(Xte).items()}
    new_activity = [scores(yte[new], pte_cal[new], "LightGBM v2 (calibrated)", new_refs),
                    scores(yte[new], freq(Xte)[new], "2026 frequency to date")]
    regions = region_of(Xte.cell_lat.to_numpy(), Xte.cell_lon.to_numpy())
    per_region = []
    for name in list(REGIONS) + ["Other"]:
        m = regions == name
        if m.sum() >= 500:
            per_region.append({"region": name, **scores(yte[m], pte_cal[m], "LightGBM v2 (calibrated)",
                                                        {k: v[m] for k, v in refs(Xte).items()})})
    bins = cfg.risk["risk_bins"]
    levels = np.digitize(pte_cal, bins)
    level_rates = [{"level": cfg.risk["risk_labels"][k], "from": ([0] + bins)[k], "to": (bins + [1])[k],
                    "n": int((levels == k).sum()),
                    "observed_rate": round(float(yte[levels == k].mean()), 4) if (levels == k).any() else None}
                   for k in range(len(bins) + 1)]

    rounds = bundle.get("best_iteration") or model.num_trees()
    spatial = [spatial_blocks(Xtr, ytr, feats, rounds),
               spatial_blocks(Xtr, ytr, [f for f in feats if f not in ("cell_lat", "cell_lon")], rounds)]
    sample = Xte.sample(min(50_000, len(Xte)), random_state=0)
    contrib = model.predict(sample[feats], pred_contrib=True)[:, :-1]
    importance = sorted(({"feature": f, "gain": round(float(g), 1), "mean_abs_contribution": round(float(c), 4)}
                         for f, g, c in zip(feats, model.feature_importance("gain"), np.abs(contrib).mean(0))),
                        key=lambda d: -d["gain"])

    result = {"model": model_dir.name, "label": bundle.get("label"),
              "blocks": {"train": span(blocks.train), "validation": span(blocks.validation), "test": span(blocks.test)},
              "rows": {"train": len(ytr), "validation": len(yva), "test": len(yte)},
              "test": test, "new_activity_subset": new_activity, "per_region": per_region,
              "risk_levels_on_test": level_rates, "spatial_block_cv_on_train": spatial,
              "reliability_test_raw": reliability(yte, pte), "reliability_test_calibrated": reliability(yte, pte_cal),
              "importance": importance, "persistence_probabilities": {"fire_in_last_7_days": p1, "none": p0},
              "v1_for_comparison": "v1 reported ROC-AUC 0.884 / PR-AUC 0.797 / Brier 0.114 on its own validation "
                                   "weeks, with early stopping on those same weeks and a different label "
                                   "(any sensor); not comparable and slightly optimistic."}
    reports.mkdir(parents=True, exist_ok=True)
    (reports / "risk_evaluation.json").write_text(json.dumps(result, indent=2) + "\n")
    plot_reliability(result, figures / "risk_reliability.png")

    meta = artifact.read_meta(model_dir)
    meta.update({"test": [{k: r[k] for k in ("model", "roc_auc", "pr_auc", "brier")} for r in test[:1] + test[2:3]],
                 "test_scored": True, "calibration": {"method": "isotonic, fitted on the validation block",
                                                      "x": cal[0], "y": cal[1]}})
    (model_dir / artifact.META).write_text(json.dumps(meta, indent=2, default=str) + "\n")
    write_card(result, card)
    print(pd.DataFrame(test).to_string(index=False))
    print(f"wrote {reports / 'risk_evaluation.json'}, {card}  [{time.time() - t0:.0f}s]")
    return result


def plot_reliability(result: dict, path: Path) -> Path:
    fig, ax = plt.subplots(figsize=(5, 5), constrained_layout=True)
    ax.plot([0, 1], [0, 1], color="#77756f", lw=1, ls="--", label="perfectly calibrated")
    for key, color, label in (("reliability_test_raw", "#eb6834", "raw"),
                              ("reliability_test_calibrated", "#2a78d6", "calibrated (isotonic, validation)")):
        r = result[key]
        ax.plot([b["mean_predicted"] for b in r], [b["observed_rate"] for b in r], "o-", color=color, lw=2, label=label)
    ax.set_xlabel("predicted probability")
    ax.set_ylabel("observed rate (test block)")
    ax.set_title(f"Reliability on the test block {result['blocks']['test'][0]} to {result['blocks']['test'][1]}",
                 fontsize=9)
    ax.legend(frameon=False, fontsize=8)
    ax.grid(alpha=0.3)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=120)
    plt.close(fig)
    return path


def _row(r: dict, cols=("roc_auc", "pr_auc", "brier", "bss_vs_persistence", "bss_vs_frequency_to_date")) -> str:
    fmt = lambda v: "n/a" if v is None else f"{v:.3f}"
    return f"| {r.get('region', r['model'])} | {r['n']:,} | " + " | ".join(fmt(r.get(c)) for c in cols) + " |"


def write_card(r: dict, path: Path) -> Path:
    head = "| | rows | ROC-AUC | PR-AUC | Brier | BSS vs persistence | BSS vs frequency to date |\n|---|---|---|---|---|---|---|"
    t = r["test"][0]
    lines = [
        "# Model card: F.I.R.E.S. 7-day fire risk (v2)",
        "",
        "Generated by `python -m godseye evaluate` from `reports/risk_evaluation.json`. Every number below comes from "
        f"the **untouched test block ({r['blocks']['test'][0]} to {r['blocks']['test'][1]})**, scored once.",
        "",
        "## Intended use",
        "",
        "A planning aid for **regional burning activity** over the next 7 days, per 0.25° cell: which areas are likely to "
        "see satellite-detected fire. It is **not** a prediction of ignitions, fire spread or danger to people, and it "
        "should not drive emergency decisions on its own.",
        "",
        "## Data and label",
        "",
        f"- Label: {r['label']} (ADR 0004). One reference satellite keeps the base rate stable while satellites "
        "come and go.",
        "- Features: NOAA-20 only, all computed from data on or before the issue date (fire days, fire cells, "
        "detections, FRP, night share, streaks, neighbouring cells, location, recent NOAA-20 outages).",
        "- Data: NASA FIRMS VIIRS 375 m (NOAA-20, VJ114IMG), 2026-01-01 to 2026-11-06, global.",
        f"- Weekly issue dates, three blocks separated by the 7-day horizon (ADR 0005): train {r['blocks']['train'][0]} "
        f"to {r['blocks']['train'][1]} ({r['rows']['train']:,} cell-weeks), validation {r['blocks']['validation'][0]} to "
        f"{r['blocks']['validation'][1]} ({r['rows']['validation']:,}; early stopping and calibration), test "
        f"{r['blocks']['test'][0]} to {r['blocks']['test'][1]} ({r['rows']['test']:,}).",
        "",
        "## Results on the test block",
        "",
        head, *[_row(x) for x in r["test"]],
        "",
        f"ROC-AUC is a ranking measure, not accuracy. Brier score: lower is better. Brier skill score (BSS) > 0 means "
        f"better than that baseline. Positive rate on the test block: {t['positive_rate']:.1%}.",
        "",
        "### New activity (no fire in the cell in the previous 30 days)",
        "",
        head, *[_row(x) for x in r["new_activity_subset"]],
        "",
        "This is where a forecast has to add value beyond \"it was burning last week\".",
        "",
        "### By region",
        "",
        head, *[_row(x) for x in r["per_region"]],
        "",
        "### Calibration and risk levels",
        "",
        "Probabilities are calibrated with isotonic regression fitted on the validation block "
        "(`reports/figures/risk_reliability.png`). Observed rate on the test block per risk level:",
        "",
        "| level | calibrated probability | cells | observed rate |",
        "|---|---|---|---|",
        *[f"| {x['level']} | {x['from']:.1f} to {x['to']:.1f} | {x['n']:,} | "
          f"{'n/a' if x['observed_rate'] is None else f'{x['observed_rate']:.1%}'} |" for x in r["risk_levels_on_test"]],
        "",
        "### Does it memorize places? (5° spatial blocks, train block)",
        "",
        "| variant | rows | ROC-AUC | PR-AUC | Brier |", "|---|---|---|---|---|",
        *[_row(x, ("roc_auc", "pr_auc", "brier")) for x in r["spatial_block_cv_on_train"]],
        "",
        "If dropping latitude/longitude barely changes the held-out-blocks score, the model is not relying on "
        "memorized locations.",
        "",
        "### What drives it",
        "",
        "| feature | gain | mean absolute contribution |", "|---|---|---|",
        *[f"| {x['feature']} | {x['gain']:,.0f} | {x['mean_abs_contribution']:.3f} |" for x in r["importance"][:10]],
        "",
        "## Comparison with v1",
        "",
        f"{r['v1_for_comparison']}",
        "",
        "## Limitations and failure modes",
        "",
        "- **Persistence dominates:** recent fire in the cell and its neighbours is the strongest signal. The skill that "
        "matters is on the new-activity subset above.",
        "- **Cells that never burned are not scored:** only cells with NOAA-20 fire since 2026-01-01 get a forecast.",
        "- **Cropland and other managed burning count as fire:** the label is satellite-detected thermal activity, not "
        "wildfire only.",
        "- **Clouds and outages:** a missed detection looks like no fire. NOAA-20 outages are dropped from labels, "
        "clouds are not.",
        "- **One year of data:** no seasonal features yet. Validation and test are Aug–Oct, so other seasons are "
        "untested.",
        "",
        "## Ethical notes",
        "",
        "Fire is often set on purpose (agriculture, land clearing). A high score is not evidence of wrongdoing and must "
        "not be used to target communities. Public data only; no personal data.",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
