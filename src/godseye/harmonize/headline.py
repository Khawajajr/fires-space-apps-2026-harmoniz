"""
Fallback headline figure (ticket 06): "same fires, different camera".

For one AOI: weekly raw S-NPP vs raw Aqua (the gap is the sensor, not the fire), next to the Aqua-equivalent estimate
vs Aqua observed. Every estimate is held out: each month is mapped with a link fitted without that month, on days both
sensors delivered full data, so the right-hand panel shows out-of-sample agreement, not a fit to itself.
"""
from __future__ import annotations

import warnings
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


VIIRS = ["S-NPP-VIIRS", "NOAA-20-VIIRS", "NOAA-21-VIIRS"]


def _year_mean(a: np.ndarray) -> np.ndarray:
    with np.errstate(all="ignore"), warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        return np.nanmean(a, axis=1)


def switchover_series(store, chain, bbox, switch_after: int) -> pd.DataFrame:
    """Per year for one AOI (mean weekly fire cell-days, so 2026's partial year compares): the naive record (Aqua-MODIS
    raw to `switch_after`, then every VIIRS satellite's raw counts added up: the wrong way, shown as the problem),
    Aqua raw, the harmonized Aqua-equivalent with its band, and S-NPP mapped to Aqua-equivalent in every year."""
    import dataclasses

    cal = store.calendar(bbox, "cell_days", "week")
    raw = {s: cal.values[store.sensors.index(s)] for s in [chain.target, *VIIRS]}
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        viirs = np.where(np.all([np.isnan(raw[s]) for s in VIIRS], axis=0), np.nan,
                         np.nansum([raw[s] for s in VIIRS], axis=0))
    store.attach_chain(chain)
    h = store.harmonized(bbox, "week")
    store.attach_chain(dataclasses.replace(chain, observed_until=None))   # VIIRS estimate in every year
    est = store.harmonized(bbox, "week")
    store.attach_chain(chain)
    years = np.asarray(cal.years)
    naive = np.where((years <= switch_after)[:, None], raw[chain.target], viirs)
    return pd.DataFrame({"year": years, "naive": _year_mean(naive), "aqua": _year_mean(raw[chain.target]),
                         "harmonized": _year_mean(h.values), "lo": _year_mean(h.lo), "hi": _year_mean(h.hi),
                         "snpp_as_aqua": _year_mean(est.values)})


def plot_switchover(series: dict[str, pd.DataFrame], switch_after: int, observed_until: int,
                    agreement: tuple[int, int], last_day: str, path: Path) -> Path:
    fig, axes = plt.subplots(1, len(series), figsize=(max(10, 7 * len(series)), 5.6), constrained_layout=True,
                             squeeze=False)
    for i, (ax, (label, s)) in enumerate(zip(axes[0], series.items())):
        ax.axvspan(observed_until + 0.5, s.year.max() + 0.5, color="#77756f", alpha=0.07, lw=0)
        ax.fill_between(s.year, s.lo, s.hi, color="#1baf7a", alpha=0.2, lw=0, label="harmonized: 90% range")
        ax.plot(s.year, s.naive, "o-", color="#e34948", lw=2, ms=4,
                label=f"naive record: Aqua-MODIS raw to {switch_after}, then all VIIRS satellites added up")
        ax.plot(s.year, s.aqua, "s--", color="#77756f", lw=1.2, ms=3, label="Aqua-MODIS raw")
        ax.plot(s.year, s.harmonized, "o-", color="#1baf7a", lw=2.6, ms=4, label="harmonized: Aqua-equivalent")
        a = s[s.year.between(*agreement)]
        ax.plot(a.year, a.snpp_as_aqua, "D", color="#2a78d6", ms=5, mfc="none", mew=1.5,
                label=f"agreement check: S-NPP mapped to Aqua-equivalent, {agreement[0]}-{agreement[1]}")
        vals = s[["naive", "aqua", "lo", "hi", "harmonized"]].to_numpy()
        top, bottom = np.nanmax(vals), np.nanmin(vals[vals > 0])
        ax.set_yscale("log")
        ax.set_ylim(bottom / 3, top * 4)
        for x, text, y in ((switch_after + 0.5, "simulated switch MODIS → VIIRS", 3.2),
                           (2018.25, "+ NOAA-20 (Apr 2018)", 2.0), (2023.17, "+ NOAA-21 (Mar 2023)", 1.25)):
            ax.axvline(x, color="#77756f", lw=0.8, ls=":")
            ax.text(x + 0.08, top * y, text, fontsize=7.5, color="#55534e", va="center")
        ax.text(observed_until + 0.6, bottom / 2.2, "Aqua orbit drifting →", fontsize=7.5, color="#55534e")
        ax.set_title(label, fontsize=11, loc="left")
        ax.set_ylabel("mean weekly fire cell-days (log scale)")
        ax.set_xticks(s.year[::2])
        ax.grid(alpha=0.3, which="both")
    fig.legend(*axes[0, 0].get_legend_handles_labels(), loc="outside lower center", fontsize=8, frameon=False,
               ncol=2 if len(series) == 1 else 3)
    fig.suptitle(f"Same fires, changing satellites: the raw record jumps, the harmonized record doesn't\n"
                 f"(2026 to {last_day}; the {switch_after}/{switch_after + 1} MODIS → VIIRS switch is simulated "
                 f"inside the real overlap)", fontsize=11)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=130)
    plt.close(fig)
    return path
