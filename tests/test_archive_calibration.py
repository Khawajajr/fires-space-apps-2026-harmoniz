"""Ticket 08: with the global multi-year record ingested, every link is refitted on it (headline: 2013-2021)."""
import json
from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from godseye.config import load_config
from godseye.harmonize import pipeline as harmonize
from godseye.ingest.aggregate import availability

REGIONS = [(35.0, 35.0), (-35.0, -65.0), (5.0, 25.0), (55.0, 125.0)]       # 10° block centres
LEVANT = [(31.875, 35.875), (32.125, 36.125), (33.375, 36.375)]           # 0.25° cells
RATIOS = {"S-NPP-VIIRS": 1.0, "NOAA-20-VIIRS": 1.0, "NOAA-21-VIIRS": 0.97}
STARTS = {"S-NPP-VIIRS": "2013-01-01", "NOAA-20-VIIRS": "2018-04-01", "NOAA-21-VIIRS": "2023-03-01",
          "Aqua-MODIS": "2013-01-01", "Terra-MODIS": "2013-01-01"}


def aqua_ratio(d):
    return 0.25 if d.year <= 2021 else 0.25 * (1 - 0.05 * (d.year - 2021))   # orbit drift after 2021


def rows_for(cells, days, rng, mean):
    rows = []
    for d in days:
        season = 1 + 0.8 * np.sin(2 * np.pi * d.dayofyear / 365)
        for lat, lon in cells:
            base = rng.poisson(mean * season)
            for s, r in RATIOS.items():
                if d >= pd.Timestamp(STARTS[s]):
                    n = rng.poisson(base * r)
                    if n:
                        rows.append((s, d, lat, lon, n, n, n, float(n)))
            n = rng.poisson(base * aqua_ratio(d))
            if n:
                rows.append(("Aqua-MODIS", d, lat, lon, n, n, n, float(n)))
    return rows


def frame(rows, sensors):
    g = pd.DataFrame(rows, columns=["sensor", "acq_date", "cell_lat", "cell_lon", "n_detections", "n_fire_cells",
                                    "n_fire_cells_daytime", "frp_sum_mw"])
    g["sensor"] = pd.Categorical(g.sensor, categories=sensors)
    return g


def status_table(sensors, days):
    a = pd.DataFrame([(s, d, "ok" if d >= pd.Timestamp(STARTS[s]) else "not_operational")
                      for s in sensors for d in days], columns=["sensor", "acq_date", "status"])
    a["sensor"] = pd.Categorical(a.sensor, categories=sensors)
    a["status_own_rule"] = a.status
    return a


@pytest.fixture(scope="module")
def run(tmp_path_factory):
    root = tmp_path_factory.mktemp("d")
    cfg = load_config(env={"GODSEYE_DATA_DIR": str(root)})
    cfg = replace(cfg, figures_dir=root / "figures")
    sensors = list(cfg.sensors)
    rng = np.random.default_rng(5)
    proc = cfg.processed_dir
    (proc / "archive").mkdir(parents=True)
    (proc / "aoi" / "levant").mkdir(parents=True)

    days26 = pd.date_range("2026-01-01", "2026-10-31")
    g26 = frame(rows_for(LEVANT, days26, rng, 20), sensors)
    g26.to_feather(proc / "sensor_grid_daily.feather")
    availability(g26, cfg.sensors, 0.2).to_feather(proc / "sensor_availability.feather")
    pd.DataFrame({"satellite": ["Aqua", "Suomi-NPP"], "acq_datetime": pd.to_datetime(["2026-07-01 10:30Z"] * 2),
                  "longitude": [35.9, 35.9], "daynight": ["D", "D"]}).to_feather(proc / "fires_clean.feather")

    days = pd.date_range("2013-01-01", "2026-10-31")
    frame(rows_for(REGIONS, days, rng, 60), sensors).to_feather(proc / "archive" / "region_daily.feather")
    status_table(sensors, days).to_feather(proc / "archive" / "sensor_availability.feather")
    frame(rows_for(LEVANT, days, rng, 15), sensors).to_feather(proc / "aoi" / "levant" / "sensor_grid_daily.feather")
    status_table(sensors, days).to_feather(proc / "aoi" / "levant" / "sensor_availability.feather")

    links = harmonize.run(cfg, proc, root / "reports")
    report = json.loads((root / "reports" / harmonize.REPORT).read_text())
    return cfg, links, {r["source"]: r for r in report["links"]}


def test_headline_link_is_fitted_on_2013_2021_by_year_and_is_not_provisional(run):
    cfg, links, report = run
    head = report["S-NPP-VIIRS"]
    assert head["calibration_window"] == "2013-2021" and head["folds"] == [str(y) for y in range(2013, 2022)]
    assert head["provisional"] is False and head["month_effects_validated"] is True
    link = next(k for k in links if k.target == "Aqua-MODIS")
    assert link.ratios() == pytest.approx(0.25, abs=0.01)
    assert not any(c.startswith("provisional") for c in head["caveats"])


def test_drift_check_finds_the_simulated_orbit_drift(run):
    cfg, links, report = run
    d = report["S-NPP-VIIRS"]["drift_check"]
    assert d["from_year"] == 2022 and d["mean_ratio_in_window"] == pytest.approx(1, abs=0.03)
    assert d["trend_per_year_after_window"] < -0.03 and d["mean_ratio_after_window"] < 0.95


def test_viirs_links_use_their_whole_multi_year_overlap(run):
    cfg, links, report = run
    assert report["NOAA-20-VIIRS"]["calibration_window"] == "2018-2026"
    assert report["NOAA-21-VIIRS"]["calibration_window"] == "2023-2026"
    n21 = next(k for k in links if k.source == "NOAA-21-VIIRS")
    assert n21.ratios() == pytest.approx(1 / 0.97, abs=0.01)


def test_switchover_figure_replaces_the_2026_figure(run):
    cfg, links, report = run
    assert (cfg.figures_dir / "headline_switchover.png").stat().st_size > 0
    assert not (cfg.figures_dir / "headline_same_fires_different_camera.png").exists()
