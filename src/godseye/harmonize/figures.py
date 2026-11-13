"""Figures for the harmonization report."""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

from godseye.harmonize.link import Link  # noqa: E402


def plot_links(links: list[Link], path: Path, title: str) -> Path:
    """Monthly ratio target / source on paired days, with the shipped link and its bootstrap interval."""
    fig, ax = plt.subplots(figsize=(9, 4), constrained_layout=True)
    colors = ["#2a78d6", "#eb6834", "#1baf7a", "#6250d6"]
    for i, link in enumerate(links):
        color = colors[i % len(colors)]
        drift = pd.DataFrame(link.report["monthly_drift"])
        x = pd.to_datetime(drift.month)
        label = f"{link.source} vs {link.target}"
        ax.plot(x, drift.ratio_y_over_x, "o-", color=color, lw=2, ms=5, label=f"{label}: monthly ratio")
        lo, _, hi = link.report["global_ratio_bootstrap_90"]
        ax.axhspan(lo, hi, color=color, alpha=0.12)
        ax.axhline(link.ratios(), color=color, lw=1, ls="--",
                   label=f"shipped: {link.method.replace('_', ' ')} ({link.ratios():.3f})")
    ax.axhline(1.0, color="#77756f", lw=0.8)
    ax.set_ylabel(f"{links[0].target} fire cell-days / other sensor")
    ax.set_title(title)
    ax.grid(alpha=0.3)
    ax.legend(fontsize=8, frameon=False, loc="lower left")
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=120)
    plt.close(fig)
    return path
