"""Sensor x date coverage chart: availability status per day, and global daily detections per sensor."""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.colors import ListedColormap  # noqa: E402

from godseye.ingest.aggregate import STATUSES  # noqa: E402

STATUS_COLORS = {"ok": "#2a9d8f", "partial": "#e9c46a", "no_data": "#e76f51", "not_operational": "#d9d9d9"}


def plot_coverage(avail: pd.DataFrame, path: Path, title: str) -> Path:
    sensors = list(avail.sensor.cat.categories)
    dates = np.sort(avail.acq_date.unique())
    wide = avail.pivot(index="sensor", columns="acq_date", values="status").reindex(index=sensors, columns=dates)
    codes = np.vectorize(STATUSES.index)(wide.astype(str).to_numpy())

    fig, (top, bottom) = plt.subplots(2, 1, figsize=(12, 5.5), sharex=True, height_ratios=[1, 1.4],
                                      constrained_layout=True)
    x = pd.to_datetime(dates)
    top.pcolormesh(np.r_[x, x[-1] + pd.Timedelta(days=1)], np.arange(len(sensors) + 1), codes,
                   cmap=ListedColormap([STATUS_COLORS[s] for s in STATUSES]), vmin=-0.5, vmax=len(STATUSES) - 0.5)
    top.set_yticks(np.arange(len(sensors)) + 0.5, sensors)
    top.invert_yaxis()
    top.set_title(title)
    top.legend(handles=[plt.Rectangle((0, 0), 1, 1, color=STATUS_COLORS[s]) for s in STATUSES],
               labels=[s.replace("_", " ") for s in STATUSES], loc="upper left", bbox_to_anchor=(1.0, 1.0),
               frameon=False)

    for name in sensors:
        s = avail[avail.sensor == name].set_index("acq_date").n_detections_global
        bottom.plot(pd.to_datetime(s.index), s.where(s > 0).to_numpy(), lw=1, label=name)
    bottom.set_yscale("log")
    bottom.set_ylabel("global detections / day")
    bottom.legend(loc="upper left", bbox_to_anchor=(1.0, 1.0), frameon=False)
    bottom.grid(alpha=0.3)

    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=110)
    plt.close(fig)
    return path
