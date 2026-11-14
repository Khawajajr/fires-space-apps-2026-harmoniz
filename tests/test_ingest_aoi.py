"""Ticket 07: multi-year AOI ingest from FIRMS archive downloads (synthetic archive files)."""
import json
import shutil
from dataclasses import replace

import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from godseye.api import calendar as calendar_api
from godseye.calendar.store import CalendarStore
from godseye.cli import main
from godseye.config import load_config
from godseye.ingest import aoi as aoi_ingest

HEADER = ",".join(["latitude", "longitude", "brightness", "scan", "track", "acq_date", "acq_time", "satellite",
                   "instrument", "confidence", "version", "bright_t31", "frp", "daynight", "type"])
MODIS = VIIRS = HEADER


def write_archive(folder):
    """Two years of summer fires in Jordan for Aqua and S-NPP, plus rows outside the Levant and one duplicate."""
    rows_m, rows_v = [], []
    for year in (2019, 2020):
        for day in pd.date_range(f"{year}-07-01", f"{year}-07-14"):
            d = day.strftime("%Y-%m-%d")
            rows_m.append(f"31.95,35.93,320,1,1,{d},1030,Aqua,MODIS,80,61.03,300,12.5,D,0")
            rows_v.append(f"31.95,35.93,330,0.4,0.4,{d},1050,N,VIIRS,n,2,295,3.2,D,0")
            rows_v.append(f"31.96,35.97,331,0.4,0.4,{d},1050,N,VIIRS,h,2,295,4.2,D,0")
    rows_m.append("10.0,10.0,320,1,1,2019-07-01,1030,Aqua,MODIS,80,61.03,300,12.5,D,0")      # outside the Levant
    # the same detection as in the 2026 fixture (edge_viirs_nrt.csv, NOAA-20 at 11:07): a duplicate across sources
    rows_v.append("31.95,35.93,331.1,0.4,0.4,2026-08-03,1107,N20,VIIRS,n,2,295.0,2.2,D,0")
    (folder / "DL_FIRE_M-C61_1").mkdir(parents=True)
    (folder / "DL_FIRE_SV-C2_2").mkdir(parents=True)
    (folder / "DL_FIRE_M-C61_1" / "fire_archive_M-C61_1.csv").write_text("\n".join([MODIS, *rows_m]) + "\n")
    (folder / "DL_FIRE_SV-C2_2" / "fire_archive_SV-C2_2.csv").write_text("\n".join([VIIRS, *rows_v]) + "\n")


@pytest.fixture(scope="module")
def ingested(tmp_path_factory, fixture_dir_module):
    root = tmp_path_factory.mktemp("data")
    shutil.copytree(fixture_dir_module, root / "raw" / "fixture")
    write_archive(root / "archive")
    cfg = replace(load_config(env={"GODSEYE_DATA_DIR": str(root)}), figures_dir=root / "figures")
    main(["clean", str(root / "raw"), "--out", str(cfg.processed_dir)])
    main(["aggregate", "--clean-dir", str(cfg.processed_dir), "--out", str(cfg.processed_dir),
          "--figure", str(root / "cov.png")])
    report = aoi_ingest.run(cfg, "levant", root / "archive")
    return cfg, root, report


@pytest.fixture(scope="module")
def fixture_dir_module():
    from tests.conftest import FIXTURE_DIR
    return FIXTURE_DIR


def test_archive_years_are_ingested_inside_the_aoi_only(ingested):
    cfg, root, report = ingested
    assert report["first_day"] == "2019-07-01" and report["rows_outside_aoi"] > 0
    assert report["earliest_year"]["Aqua-MODIS"] == 2019 and report["earliest_year"]["S-NPP-VIIRS"] == 2019
    clean = pd.read_feather(cfg.processed_dir / "aoi" / "levant" / "fires_clean.feather")
    assert clean.latitude.between(29, 37.5).all() and clean.longitude.between(34, 42.5).all()


def test_the_same_detection_in_archive_and_2026_files_is_kept_once(ingested):
    cfg, root, report = ingested
    # The 2026 copy is NRT and the archive copy is standard: archive wins for that satellite-day.
    assert report["dropped_nrt_superseded_by_archive"] >= 1
    clean = pd.read_feather(cfg.processed_dir / "aoi" / "levant" / "fires_clean.feather")
    dup = clean[(clean.satellite.astype(str) == "NOAA-20") & (clean.acq_date.astype(str) == "2026-08-03")]
    assert len(dup) == 1 and dup["product"].astype(str).item() == "archive"


def test_aoi_only_years_are_never_called_outages(ingested):
    cfg, root, report = ingested
    a = pd.read_feather(cfg.processed_dir / "aoi" / "levant" / "sensor_availability.feather")
    aqua_2019 = a[(a.sensor.astype(str) == "Aqua-MODIS") & (pd.to_datetime(a.acq_date).dt.year == 2019)]
    assert set(aqua_2019.status.astype(str)) == {"ok"} and set(aqua_2019.basis) == {"aoi_archive"}
    n21_2019 = a[(a.sensor.astype(str) == "NOAA-21-VIIRS") & (pd.to_datetime(a.acq_date).dt.year == 2019)]
    assert set(n21_2019.status.astype(str)) == {"not_operational"}          # launched 2024
    assert (a[pd.to_datetime(a.acq_date).dt.year == 2026].basis == "global").all()


def test_report_and_rerun_are_stable(ingested):
    cfg, root, report = ingested
    saved = json.loads((cfg.processed_dir / "aoi" / "levant" / "ingest_report.json").read_text())
    assert saved["gate"]["status"] == "insufficient_history"                 # 2 summers of synthetic data
    before = pd.read_feather(cfg.processed_dir / "aoi" / "levant" / "sensor_grid_daily.feather")
    aoi_ingest.run(cfg, "levant", root / "archive")
    after = pd.read_feather(cfg.processed_dir / "aoi" / "levant" / "sensor_grid_daily.feather")
    pd.testing.assert_frame_equal(before, after)


def test_requests_inside_an_ingested_aoi_use_its_multi_year_store(ingested):
    cfg, root, report = ingested
    d = cfg.processed_dir / "aoi" / "levant"
    aoi_store = CalendarStore(pd.read_feather(d / "sensor_grid_daily.feather"),
                              pd.read_feather(d / "sensor_availability.feather"), 0.25)
    global_store = CalendarStore(pd.read_feather(cfg.processed_dir / "sensor_grid_daily.feather"),
                                 pd.read_feather(cfg.processed_dir / "sensor_availability.feather"), 0.25)
    app = FastAPI()
    app.include_router(calendar_api.router)
    calendar_api.STORE.update({"calendar": global_store, "aoi": {"levant": (cfg.aois["levant"].bbox, aoi_store)}})
    try:
        with TestClient(app) as c:
            jordan = c.get("/api/calendar", params={"aoi": "jordan"}).json()       # inside the Levant
            argentina = c.get("/api/calendar", params={"aoi": "argentina"}).json()
    finally:
        calendar_api.STORE.clear()
    assert jordan["years"][0] == 2019 and jordan["data_range"][0] == "2019-07-01"
    assert argentina["years"] == [2026]
