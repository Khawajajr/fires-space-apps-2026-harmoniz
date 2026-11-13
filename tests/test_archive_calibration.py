"""Ticket 08: the headline link is calibrated on the archive's pre-drift years when they are ingested."""
import json
from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from godseye.config import load_config
from godseye.harmonize import pipeline as harmonize
from godseye.ingest.aggregate import availability

LEVANT = [(31.875, 35.875), (32.125, 36.125), (33.375, 36.375)]
ELSEWHERE = [(-24.125, 31.375), (-10.125, 25.375), (12.125, 105.375)]


def grid_rows(sensor, dates, cells, mean, rng, ratio=1.0, base=None):
    rows = []
    for d in dates:
        season = 1.0 + 0.8 * np.sin(2 * np.pi * d.dayofyear / 365)
        for lat, lon in cells:
            n = rng.poisson(mean * season * ratio) if base is None else rng.poisson(ratio * base[(d, lat, lon)])
            if n:
                rows.append((sensor, d, lat, lon, n, n, n, float(n)))
    return rows


def frame(rows, sensors):
    g = pd.DataFrame(rows, columns=["sensor", "acq_date", "cell_lat", "cell_lon", "n_detections", "n_fire_cells",
                                    "n_fire_cells_daytime", "frp_sum_mw"])
    g["sensor"] = pd.Categorical(g.sensor, categories=sensors)
    return g


def write_store(folder, grid, avail):
    folder.mkdir(parents=True, exist_ok=True)
    grid.reset_index(drop=True).to_feather(folder / "sensor_grid_daily.feather")
    avail.reset_index(drop=True).to_feather(folder / "sensor_availability.feather")


@pytest.fixture(scope="module")
def run(tmp_path_factory):
    root = tmp_path_factory.mktemp("d")
    cfg = load_config(env={"GODSEYE_DATA_DIR": str(root)})
    cfg = replace(cfg, figures_dir=root / "figures")
    sensors = list(cfg.sensors)
    rng = np.random.default_rng(5)

    # global 2026: every VIIRS pair and Aqua, on six cells around the world
    days26 = pd.date_range("2026-01-01", "2026-10-31")
    snpp = {}
    rows = []
    for d in days26:
        for lat, lon in LEVANT + ELSEWHERE:
            snpp[(d, lat, lon)] = rng.poisson(40 * (1 + 0.8 * np.sin(2 * np.pi * d.dayofyear / 365)))
    rows += [("S-NPP-VIIRS", d, la, lo, n, n, n, float(n)) for (d, la, lo), n in snpp.items() if n]
    for s, r in (("NOAA-20-VIIRS", 1.0), ("NOAA-21-VIIRS", 0.97), ("Aqua-MODIS", 0.2)):
        rows += grid_rows(s, days26, LEVANT + ELSEWHERE, 0, rng, r, snpp)
    g26 = frame(rows, sensors)
    a26 = availability(g26.rename(columns={}), cfg.sensors, 0.2)
    write_store(cfg.processed_dir, g26, a26)
    clean = pd.DataFrame({"satellite": ["Aqua", "Suomi-NPP"], "acq_datetime": pd.to_datetime(["2026-07-01 10:30Z"] * 2),
                          "longitude": [35.9, 35.9], "daynight": ["D", "D"]})
    clean.to_feather(cfg.processed_dir / "fires_clean.feather")

    # Levant archive 2018-2025: Aqua sees 25% of S-NPP before its drift
    days = pd.date_range("2018-01-01", "2025-12-31")
    base, rows = {}, []
    for d in days:
        for lat, lon in LEVANT:
            base[(d, lat, lon)] = rng.poisson(30 * (1 + 0.8 * np.sin(2 * np.pi * d.dayofyear / 365)))
    rows += [("S-NPP-VIIRS", d, la, lo, n, n, n, float(n)) for (d, la, lo), n in base.items() if n]
    rows += grid_rows("Aqua-MODIS", days, LEVANT, 0, rng, 0.25, base)
    garch = frame(rows, sensors)
    aarch = pd.DataFrame([(s, d, "ok" if s in ("S-NPP-VIIRS", "Aqua-MODIS") else "not_operational")
                          for s in sensors for d in days], columns=["sensor", "acq_date", "status"])
    aarch["sensor"] = pd.Categorical(aarch.sensor, categories=sensors)
    aarch["status_own_rule"] = aarch.status
    write_store(cfg.processed_dir / "aoi" / "levant", garch, aarch)

    links = harmonize.run(cfg, cfg.processed_dir, root / "reports")
    report = json.loads((root / "reports" / harmonize.REPORT).read_text())
    return cfg, links, report


def test_headline_link_uses_the_pre_drift_archive_years_and_is_no_longer_provisional(run):
    cfg, links, report = run
    head = next(r for r in report["links"] if r["target"] == "Aqua-MODIS")
    assert head["calibration_window"] == "2018-2021" and head["calibration_aois"] == ["levant"]
    assert head["provisional"] is False and head["month_effects_validated"] is True
    assert head["folds"] == ["2018", "2019", "2020", "2021"]
    link = next(k for k in links if k.target == "Aqua-MODIS")
    assert link.ratios() == pytest.approx(0.25, abs=0.02)
    assert not any(c.startswith("provisional") for c in head["caveats"])


def test_drift_check_covers_the_years_after_the_window(run):
    cfg, links, report = run
    head = next(r for r in report["links"] if r["target"] == "Aqua-MODIS")
    years = sorted({row["year"] for row in head["drift_check"]})
    assert years[0] == 2022 and all(abs(r["observed_over_predicted"] - 1) < 0.1 for r in head["drift_check"])


def test_switchover_figure_replaces_the_2026_figure(run):
    cfg, links, report = run
    assert (cfg.figures_dir / "headline_switchover.png").stat().st_size > 0
    assert not (cfg.figures_dir / "headline_same_fires_different_camera.png").exists()


def test_continuity_links_still_come_from_the_2026_global_data(run):
    cfg, links, report = run
    n21 = next(r for r in report["links"] if r["source"] == "NOAA-21-VIIRS")
    assert n21["first_week"].startswith("2025-12") or n21["first_week"].startswith("2026")
