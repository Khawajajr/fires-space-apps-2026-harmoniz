"""`godseye harmonize`: fit the configured sensor links and write coefficients + report."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from godseye.clean.io import read_table, write_table
from godseye.config import Config
from godseye.harmonize import archive
from godseye.harmonize.figures import plot_links
from godseye.harmonize.headline import held_out_weekly, plot_fallback, plot_switchover, switchover_series
from godseye.harmonize.link import Link, fit_link
from godseye.harmonize.methods import GlobalRatio
from godseye.harmonize.series import paired_days, region_of, weekly_pairs
from godseye.harmonize.validate import apply_band

COEFFICIENTS = "harmonization_coefficients"
REPORT = "harmonization_report.json"


def run(cfg: Config, processed: Path, reports_dir: Path) -> list[Link]:
    h = cfg.harmonize
    grid26 = read_table(processed, "sensor_grid_daily", ["sensor", "acq_date", "cell_lat", "cell_lon", h["metric"]])
    avail26 = read_table(processed, "sensor_availability")
    record = archive.load_record(processed, h["metric"])     # ticket 08: the global 2000-2026 record, when ingested
    grid, avail = record if record is not None else (grid26, avail26)
    links = []
    for spec in h["links"]:
        src, tgt = spec["source"], spec["target"]
        days = paired_days(avail, src, tgt)
        if record is not None:
            days = archive.in_window(days, spec.get("window"))
        df = weekly_pairs(grid, days, src, tgt, h["region_deg"], h["metric"])
        years = sorted(set(days.year))
        multi_year = record is not None and len(years) >= archive.MIN_YEARS
        provisional = bool(spec.get("provisional", False)) and not multi_year
        link = fit_link(df, src, tgt, provisional, h["region_deg"])
        link.report["calibration_source"] = (
            "global FIRMS archive + 2026 (data/processed/archive)" if record is not None else "2026 global")
        link.report["calibration_window"] = f"{years[0]}-{years[-1]}" if years else None
        link.report["paired_days_per_year"] = {int(y): int(n) for y, n in pd.Series(days.year).value_counts()
                                               .sort_index().items()}
        if record is not None and spec.get("window"):
            link.report["drift_check"] = archive.drift_check(grid, avail, link, h["metric"], h["region_deg"],
                                                             spec["window"][1] + 1)
        link.report["paired_days"] = len(days)
        link.report["note"] = spec.get("note", "")
        link.report["sensitivity_without_cross_sensor_check"] = sensitivity(grid, avail, src, tgt, h, df,
                                                                            spec.get("window") if record is not None
                                                                            else None)
        days26 = paired_days(avail26, src, tgt)
        link.report["aoi_band_coverage_in_sample"] = aoi_band_coverage(grid26, days26, link, cfg, h["metric"])
        change = link.report["sensitivity_without_cross_sensor_check"]["relative_change"]
        if abs(change) > 0.01:
            link.report["caveats"].append(
                f"calibration days depend on the cross-sensor check: without it the global ratio moves {change:+.1%}"
                " (the skipped days are partial deliveries, so the checked value is used)")
        links.append(link)
        s = link.report["cv_scores"][link.method]
        print(f"  {link.source} -> {link.target} [{link.report['calibration_window']}, {len(link.report['folds'])} "
              f"folds]: {link.method}, ratio {link.ratios():.4f}, region-month WAPE {s['region_month_wape']}, "
              f"band coverage {link.report['band_coverage_out_of_fold']}")
    headline = next((k for k in links if k.target == h["headline"]["target"]), None)
    if headline is not None:
        headline.report["overpass_local_solar_time_2026"] = overpass_times(processed)
    save(links, processed, reports_dir)
    if headline is not None and headline.provisional:          # 2026 only: "same fires, different camera"
        weeks = {cfg.aois[a].label.split(" (")[0]: held_out_weekly(grid26, avail26, headline, cfg.aois[a],
                                                                   h["region_deg"], h["metric"])
                 for a in h["headline"]["figure_aois"]}
        print(f"  wrote {plot_fallback(weeks, headline, cfg.figures_dir / 'headline_same_fires_different_camera.png')}")
    elif headline is not None:                                 # multi-year: the switchover figure (ticket 08)
        fig = switchover_figure(cfg, processed, links)
        print(f"  wrote {fig}" if fig else "  no ingested AOI covers the figure AOIs: switchover figure skipped")
    span = "2000-2026" if record is not None else "2026"
    fig = plot_links(links, cfg.figures_dir / "harmonization_links.png",
                     f"Sensor links, {span}: monthly ratio on days both sensors delivered full data")
    print(f"  wrote {fig}")
    return links


def sensitivity(grid, avail, src, tgt, h, df, window=None) -> dict:
    """The cross-sensor check decides which days count as full data using the very ratio being calibrated, so
    refit on the days each sensor's own rule accepts and report how far the global ratio moves."""
    days = archive.in_window(paired_days(avail, src, tgt, status_column="status_own_rule"), window)
    loose = weekly_pairs(grid, days, src, tgt, h["region_deg"], h["metric"])
    a, b = GlobalRatio().fit(df).ratio, GlobalRatio().fit(loose).ratio
    return {"paired_days_own_rule": len(days), "global_ratio_cross_checked": round(a, 4),
            "global_ratio_own_rule": round(b, 4), "relative_change": round(b / a - 1, 4)}


def aoi_band_coverage(grid, days, link: Link, cfg: Config, metric: str) -> dict:
    """The band is calibrated on 10° region-weeks; check it on whole-AOI weekly totals too (in-sample fit, so this
    checks the band's scale transfer, not out-of-sample skill)."""
    from godseye.calendar.store import in_bbox

    out = {}
    for name, aoi in cfg.aois.items():
        g = grid[in_bbox(grid.cell_lat, grid.cell_lon, aoi.bbox) & grid.acq_date.isin(days)]
        g = g.assign(week=g.acq_date - pd.to_timedelta(g.acq_date.dt.weekday, unit="D"))
        src = g[g.sensor.astype(str) == link.source]
        # Regional links: ratio per cell (its region and month) before summing over the AOI.
        r = link.ratios(region_of(src.cell_lat.to_numpy(), src.cell_lon.to_numpy(), link.report["region_deg"]),
                        src.acq_date.dt.month.to_numpy())
        x = (src[metric].to_numpy() * r)
        weeks = sorted(set(g.week))
        mapped = pd.Series(x, index=src.week.to_numpy()).groupby(level=0).sum().reindex(weeks, fill_value=0.0)
        y = g[g.sensor.astype(str) == link.target].groupby("week")[metric].sum().reindex(weeks, fill_value=0.0)
        value = mapped.to_numpy()
        lo, hi = apply_band(value, link.band)
        y = y.to_numpy()
        out[name] = {"weeks": len(weeks), "coverage": round(float(np.mean((y >= lo - 1e-9) & (y <= hi + 1e-9))), 4),
                     "weekly_wape": round(float(np.abs(y - value).sum() / max(y.sum(), 1e-9)), 4)}
    return out


def overpass_times(processed: Path) -> dict:
    """Median local solar time (hours) of each satellite's daytime detections: measures orbit drift directly."""
    c = read_table(processed, "fires_clean", ["satellite", "acq_datetime", "longitude", "daynight"])
    c = c[c.daynight.astype(str) == "D"]
    t = c.acq_datetime
    hours = (t.dt.hour + t.dt.minute / 60 + c.longitude.astype(float) / 15) % 24
    minutes = (hours.groupby(c.satellite.astype(str), observed=True).median() * 60).round().astype(int) % (24 * 60)
    return {k: f"{m // 60:02d}:{m % 60:02d}" for k, m in minutes.items()}


def switchover_figure(cfg: Config, processed: Path, links: list[Link]) -> Path | None:
    from godseye.calendar.harmonized import build_chain
    from godseye.calendar.store import CalendarStore

    h, hl = cfg.harmonize, cfg.harmonize["headline"]
    chain = build_chain(hl, links, h["region_deg"])
    ingested = {d.name: d for d in archive.archive_dirs(cfg, processed)}
    data, last = {}, None
    for name in hl["figure_aois"]:
        if name in ingested:
            d = ingested[name]
            store = CalendarStore(read_table(d, "sensor_grid_daily"), read_table(d, "sensor_availability"),
                                  cfg.clean["grid_deg"])
            data[cfg.aois[name].label.split(" (")[0]] = switchover_series(store, chain, cfg.aois[name].bbox,
                                                                          hl["switch_after"])
            last = store.dates[-1]
    if not data:
        return None
    window = next(s["window"] for s in h["links"] if s["target"] == hl["target"])
    return plot_switchover(data, hl["switch_after"], pd.Timestamp(hl["observed_until"]).year, tuple(window),
                           f"{last:%d %b}", cfg.figures_dir / "headline_switchover.png")


def save(links: list[Link], processed: Path, reports_dir: Path) -> None:
    coef = pd.concat([k.coefficients.assign(source=k.source, target=k.target, method=k.method,
                                            provisional=k.provisional) for k in links], ignore_index=True)
    coef["region"] = coef.region.astype(str)
    write_table(coef, processed / COEFFICIENTS, "feather")
    report = {"links": [k.report for k in links]}
    for path in (processed / REPORT, reports_dir / REPORT):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, indent=2, default=str) + "\n")


def load(processed: Path) -> list[Link]:
    """Links as written by run(); the band comes from the report."""
    coef = read_table(processed, COEFFICIENTS)
    report = json.loads((processed / REPORT).read_text())["links"]
    links = []
    for r in report:
        c = coef[(coef.source == r["source"]) & (coef.target == r["target"])]
        links.append(Link(r["source"], r["target"], r["method"], c[["level", "region", "month", "ratio"]],
                          pd.DataFrame(r["band"]), r["provisional"], r))
    return links
