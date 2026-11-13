"""`godseye harmonize`: fit the configured sensor links and write coefficients + report."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from godseye.clean.io import read_table, write_table
from godseye.config import Config
from godseye.harmonize.figures import plot_links
from godseye.harmonize.link import Link, fit_link, harmonize
from godseye.harmonize.methods import GlobalRatio
from godseye.harmonize.series import paired_days, weekly_pairs

COEFFICIENTS = "harmonization_coefficients"
REPORT = "harmonization_report.json"


def run(cfg: Config, processed: Path, reports_dir: Path) -> list[Link]:
    h = cfg.harmonize
    grid = read_table(processed, "sensor_grid_daily", ["sensor", "acq_date", "cell_lat", "cell_lon", h["metric"]])
    avail = read_table(processed, "sensor_availability")
    links = []
    for spec in h["links"]:
        src, tgt = spec["source"], spec["target"]
        days = paired_days(avail, src, tgt)
        df = weekly_pairs(grid, days, src, tgt, h["region_deg"], h["metric"])
        link = fit_link(df, src, tgt, bool(spec.get("provisional", False)), h["region_deg"])
        link.report["paired_days"] = len(days)
        link.report["note"] = spec.get("note", "")
        link.report["sensitivity_without_cross_sensor_check"] = sensitivity(grid, avail, src, tgt, h, df)
        link.report["aoi_band_coverage"] = aoi_band_coverage(grid, days, link, cfg, h["metric"])
        change = link.report["sensitivity_without_cross_sensor_check"]["relative_change"]
        if abs(change) > 0.01:
            link.report["caveats"].append(
                f"calibration days depend on the cross-sensor check: without it the global ratio moves {change:+.1%}"
                " (the skipped days are partial deliveries, so the checked value is used)")
        links.append(link)
        s = link.report["cv_scores"][link.method]
        print(f"  {link.source} -> {link.target}: {link.method}, ratio {link.ratios():.4f}, "
              f"region-month WAPE {s['region_month_wape']}, band coverage {link.report['band_coverage_out_of_fold']}")
    save(links, processed, reports_dir)
    fig = plot_links(links, cfg.figures_dir / "harmonization_viirs_continuity.png",
                     "VIIRS continuity, 2026: monthly ratio on days both sensors delivered full data")
    print(f"  wrote {fig}")
    return links


def sensitivity(grid, avail, src, tgt, h, df) -> dict:
    """The cross-sensor check decides which days count as full data using the very ratio being calibrated, so
    refit on the days each sensor's own rule accepts and report how far the global ratio moves."""
    days = paired_days(avail, src, tgt, status_column="status_own_rule")
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
        week = g.acq_date - pd.to_timedelta(g.acq_date.dt.weekday, unit="D")
        w = g.assign(week=week, sensor=g.sensor.astype(str)).pivot_table(
            index="week", columns="sensor", values=metric, aggfunc="sum", fill_value=0.0)
        w = w.reindex(columns=[link.source, link.target], fill_value=0.0)
        value, lo, hi = harmonize(w[link.source].to_numpy(), link)
        y = w[link.target].to_numpy()
        out[name] = {"weeks": len(w), "coverage": round(float(np.mean((y >= lo - 1e-9) & (y <= hi + 1e-9))), 4),
                     "weekly_wape": round(float(np.abs(y - value).sum() / max(y.sum(), 1e-9)), 4)}
    return out


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
