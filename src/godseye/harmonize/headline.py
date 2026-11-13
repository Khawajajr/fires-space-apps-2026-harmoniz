"""
Fallback headline figure (ticket 06): "same fires, different camera".

For one AOI: weekly raw S-NPP vs raw Aqua (the gap is the sensor, not the fire), next to the Aqua-equivalent estimate
vs Aqua observed. Every estimate is held out: each month is mapped with a link fitted without that month, on days both
sensors delivered full data, so the right-hand panel shows out-of-sample agreement, not a fit to itself.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from godseye.calendar.harmonized import row_ratios  # noqa: E402
from godseye.calendar.store import in_bbox  # noqa: E402
from godseye.config import AOI  # noqa: E402
from godseye.harmonize import validate as V  # noqa: E402
from godseye.harmonize.link import Link  # noqa: E402
from godseye.harmonize.series import paired_days, weekly_pairs  # noqa: E402


def held_out_weekly(grid: pd.DataFrame, avail: pd.DataFrame, link: Link, aoi: AOI, region_deg: float,
                    metric: str = "n_fire_cells") -> pd.DataFrame:
    """Weekly AOI totals on paired days: source raw, target raw, and the held-out estimate with its band."""
    days = paired_days(avail, link.source, link.target)
    pairs = weekly_pairs(grid, days, link.source, link.target, region_deg, metric)
    g = grid[grid.acq_date.isin(days) & in_bbox(grid.cell_lat, grid.cell_lon, aoi.bbox)]
    g = g.assign(week=g.acq_date - pd.to_timedelta(g.acq_date.dt.weekday, unit="D"))
    g = g.assign(month=(g.week + pd.Timedelta(days=3)).dt.strftime("%Y-%m"))
    src = g[g.sensor.astype(str) == link.source]
    cv = V.cross_validate(pairs)                      # held-out predictions, for bands that never saw their month
    out, bands = [], {}
    for month in sorted(src.month.unique()):
        model = V.candidates(pairs[pairs.month != month])[link.method]
        coef = model.coefficients()
        coef = coef[coef.level != "region_month"] if not link.report.get("month_effects_validated") else coef
        fold_link = Link(link.source, link.target, link.method, coef, link.band, link.provisional, link.report)
        s = src[src.month == month]
        r = row_ratios(fold_link, s.cell_lat.to_numpy(), s.cell_lon.to_numpy(), s.acq_date.dt.month.to_numpy(),
                       region_deg)
        out.append(pd.DataFrame({"week": s.week.to_numpy(), "estimate": s[metric].to_numpy() * r}))
        rest = cv[cv.month != month]
        bands[month] = V.band_table(rest[link.method].to_numpy(), rest.y.to_numpy())
    est = pd.concat(out).groupby("week").estimate.sum()
    week_month = src.drop_duplicates("week").set_index("week").month
    by = g.assign(sensor=g.sensor.astype(str)).pivot_table(index="week", columns="sensor", values=metric,
                                                           aggfunc="sum", fill_value=0.0)
    w = pd.DataFrame({"source": by.get(link.source, 0.0), "target": by.get(link.target, 0.0)}).fillna(0.0)
    w["estimate"] = est.reindex(w.index, fill_value=0.0)
    w["lo"], w["hi"] = np.nan, np.nan
    for week, month in week_month.items():
        if week in w.index:
            lo, hi = V.apply_band(np.array([w.at[week, "estimate"]]), bands[month])
            w.loc[week, ["lo", "hi"]] = lo[0], hi[0]
    return w


def plot_fallback(weeks: dict[str, pd.DataFrame], link: Link, path: Path) -> Path:
    fig, axes = plt.subplots(len(weeks), 2, figsize=(12, 3.6 * len(weeks)), constrained_layout=True, squeeze=False)
    viirs, modis, est = "#2a78d6", "#eb6834", "#1baf7a"
    for row, (label, w) in zip(axes, weeks.items()):
        x = w.index
        raw_ratio = w.target.sum() / w.source.sum()
        ok = w.target.sum() and w.estimate.sum()
        row[0].plot(x, w.source, color=viirs, lw=2, label=f"{link.source} (raw)")
        row[0].plot(x, w.target, color=modis, lw=2, label=f"{link.target} (raw)")
        row[0].set_title(f"{label}: same fires, different camera. {link.target} sees {raw_ratio:.0%} of {link.source}",
                         fontsize=9, loc="left")
        row[1].fill_between(x, w.lo, w.hi, color=est, alpha=0.2, lw=0, label="90% range")
        row[1].plot(x, w.estimate, color=est, lw=2, label=f"{link.target}-equivalent from {link.source} (held out)")
        row[1].plot(x, w.target, color=modis, lw=2, label=f"{link.target} observed")
        agree = w.estimate.sum() / w.target.sum() if ok else float("nan")
        cover = float(((w.target >= w.lo) & (w.target <= w.hi)).mean())
        row[1].set_title(f"{label}: harmonized. Estimate/observed {agree:.2f}; {cover:.0%} of weeks in the 90% range",
                         fontsize=9, loc="left")
        for ax in row:
            ax.xaxis.set_major_formatter(mdates.DateFormatter("%b"))
            ax.set_ylabel("fire cell-days per week")
            ax.grid(alpha=0.3)
            ax.legend(fontsize=8, frameon=False, loc="upper left")
    tag = "PROVISIONAL: calibrated on 2026 (Aqua's orbit has drifted). " if link.provisional else ""
    fig.suptitle(f"{tag}Weekly fire cell-days on days both sensors delivered full data", fontsize=11)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=120)
    plt.close(fig)
    return path


def switchover_series(store, chain, bbox, switch_after: int) -> pd.DataFrame:
    """Weekly series for one AOI: the naive record (Aqua-MODIS raw up to `switch_after`, then S-NPP-VIIRS raw), the
    harmonized headline with its band, and S-NPP mapped to Aqua-equivalent in every year (the agreement check)."""
    import dataclasses

    from godseye.calendar.store import CalendarStore  # noqa: F401  (type of `store`)

    cal = store.calendar(bbox, "cell_days", "week")
    aqua, snpp = (cal.values[store.sensors.index(s)] for s in (chain.target, chain.reference))
    store.attach_chain(chain)
    h = store.harmonized(bbox, "week")
    store.attach_chain(dataclasses.replace(chain, observed_until=None))   # VIIRS estimate in every year
    est = store.harmonized(bbox, "week")
    store.attach_chain(chain)
    rows = []
    for yi, year in enumerate(cal.years):
        for w in range(52):
            try:
                day = date.fromisocalendar(year, w + 1, 4)
            except ValueError:
                continue
            naive = aqua[yi, w] if year <= switch_after else snpp[yi, w]
            rows.append({"date": pd.Timestamp(day), "naive": naive, "harmonized": h.values[yi, w],
                         "lo": h.lo[yi, w], "hi": h.hi[yi, w], "aqua": aqua[yi, w], "snpp_as_aqua": est.values[yi, w]})
    return pd.DataFrame(rows)


def plot_switchover(series: dict[str, pd.DataFrame], switch_after: int, real_2012: bool, path: Path) -> Path:
    fig, axes = plt.subplots(len(series), 1, figsize=(12, 3.4 * len(series)), constrained_layout=True, squeeze=False)
    for ax, (label, s) in zip(axes[:, 0], series.items()):
        m = s.set_index("date").resample("MS").sum(min_count=1)          # monthly totals read better over years
        ax.fill_between(m.index, m.lo, m.hi, color="#1baf7a", alpha=0.18, lw=0, label="harmonized 90% range")
        ax.plot(m.index, m.naive, color="#e34948", lw=1.6,
                label=f"naive record: Aqua-MODIS raw to {switch_after}, then S-NPP-VIIRS raw")
        ax.plot(m.index, m.harmonized, color="#1baf7a", lw=2.2, label="harmonized: Aqua-equivalent")
        early = m[m.index.year <= switch_after]
        ax.plot(early.index, early.snpp_as_aqua, color="#2a78d6", lw=1.2, ls="--",
                label="S-NPP mapped to Aqua-equivalent (agreement check)")
        ax.axvline(pd.Timestamp(f"{switch_after + 1}-01-01"), color="#77756f", lw=1, ls=":")
        ax.set_title(f"{label}: monthly fire cell-days", fontsize=10, loc="left")
        ax.grid(alpha=0.3)
        ax.legend(fontsize=8, frameon=False, loc="upper left")
    kind = "The 2012 MODIS-to-VIIRS transition" if real_2012 else \
        f"Simulated sensor switchover (MODIS until {switch_after}, VIIRS from {switch_after + 1})"
    fig.suptitle(f"{kind}: the jump is the satellite, not the fire", fontsize=11)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=120)
    plt.close(fig)
    return path
