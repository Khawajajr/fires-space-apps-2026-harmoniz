"""Ticket 07 (rescoped): one pass over archive zips -> AOI stores, calibration regions, availability, climatology."""
import json
import zipfile
from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from godseye.config import load_config
from godseye.ingest import archive
from godseye.ingest.aggregate import availability

HEADER = "latitude,longitude,brightness,scan,track,acq_date,acq_time,satellite,instrument,confidence,version," \
         "bright_t31,frp,daynight,type"
SPOTS = [(32.0012, 36.0012), (31.5, 35.9), (-30.2, -60.1), (10.3, 20.4)]     # Jordan, Jordan, Argentina, elsewhere
GAP = "2025-06-10"


def csv_rows(days, satellite, instrument, conf, version, skip=()):
    out = [HEADER]
    for d in days:
        if str(d.date()) in skip:
            continue
        for lat, lon in SPOTS:
            out.append(f"{lat},{lon},330,1,1,{d.date()},1030,{satellite},{instrument},{conf},{version},290,5.5,D,0")
        out.append(f"{SPOTS[0][0]},{SPOTS[0][1]},330,1,1,{d.date()},1031,{satellite},{instrument},{conf},{version},"
                   "290,1.5,D,0")                                     # same fine cell: one fire cell-day
    return "\n".join(out) + "\n"


def write_zip(path, name, text):
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(name, text)
        z.writestr("Readme.txt", "FIRMS")


@pytest.fixture(scope="module")
def setup(tmp_path_factory):
    root = tmp_path_factory.mktemp("d")
    cfg = load_config(env={"GODSEYE_DATA_DIR": str(root / "data")})
    cfg = replace(cfg, figures_dir=root / "figures")
    zips = root / "zips"
    zips.mkdir()
    days = pd.date_range("2025-01-01", "2025-12-31")
    write_zip(zips / "DL_FIRE_M-C61_1.zip", "fire_archive_M-C61_1.csv",
              csv_rows(days, "Aqua", "MODIS", 80, "6.03") + csv_rows(days, "Terra", "MODIS", 80, "6.03")
              .split("\n", 1)[1])
    write_zip(zips / "DL_FIRE_J1V-C2_2.zip", "fire_archive_J1V-C2_2.csv",
              csv_rows(days, "N20", "VIIRS", "n", "2", skip={GAP}))

    # 2026 already processed (as `godseye clean` + `aggregate` leave it)
    sensors = list(cfg.sensors)
    d26 = pd.date_range("2026-01-01", "2026-01-31")
    cells = pd.DataFrame([(s, d, 3200, 3600, 2, 2, 7.0) for s in ("Aqua-MODIS", "NOAA-20-VIIRS") for d in d26],
                         columns=["sensor", "acq_date", "lat_i", "lon_i", "n_detections", "n_detections_daytime",
                                  "frp_sum_mw"])
    cells["sensor"] = pd.Categorical(cells.sensor, categories=sensors)
    cells["acq_date"] = cells.acq_date.astype("datetime64[s]")
    cfg.processed_dir.mkdir(parents=True)
    cells.to_feather(cfg.processed_dir / "sensor_fire_cells.feather")
    availability(cells, cfg.sensors, 0.2).to_feather(cfg.processed_dir / "sensor_availability.feather")
    first = archive.run(cfg, zips, workers=2)
    second = archive.run(cfg, zips, workers=2)
    return cfg, zips, first, second


def test_every_zip_is_in_the_manifest_with_rows_dates_and_sha256(setup):
    cfg, zips, first, second = setup
    files = {e["source"]["request"]: e
             for e in json.loads((cfg.data_dir / "manifest.json").read_text())["files"]}
    m = files["DL_FIRE_M-C61_1"]
    assert m["rows"] == 2 * 365 * 5 and m["first_date"] == "2025-01-01" and m["last_date"] == "2025-12-31"
    assert len(m["sha256"]) == 64 and m["sensors"] == ["Aqua-MODIS", "Terra-MODIS"]
    assert files["DL_FIRE_J1V-C2_2"]["rows"] == 364 * 5


def test_second_run_skips_ingested_zips(setup):
    cfg, zips, first, second = setup
    assert first["read"] == 2 and second["read"] == 0


def test_aoi_store_spans_archive_and_2026_with_nested_jordan(setup):
    cfg, zips, first, second = setup
    d = cfg.processed_dir / "aoi" / "levant"
    cells = pd.read_feather(d / "sensor_fire_cells.feather")
    years = set(pd.to_datetime(cells.acq_date).dt.year)
    assert years == {2025, 2026}
    n20_2025 = cells[(cells.sensor.astype(str) == "NOAA-20-VIIRS") & (pd.to_datetime(cells.acq_date).dt.year == 2025)]
    assert len(n20_2025) == 364 * 2                       # two Jordan spots, duplicate detection merged
    report = json.loads((d / "ingest_report.json").read_text())
    assert "jordan" in report["nested_gates"]
    assert (cfg.processed_dir / "aoi" / "argentina" / "sensor_grid_daily.feather").exists()


def test_availability_marks_the_missing_day_no_data_and_keeps_2026(setup):
    cfg, zips, first, second = setup
    a = pd.read_feather(cfg.processed_dir / "archive" / "sensor_availability.feather")
    a = a.assign(acq_date=pd.to_datetime(a.acq_date), sensor=a.sensor.astype(str), status=a.status.astype(str))
    n20 = a[a.sensor == "NOAA-20-VIIRS"].set_index("acq_date").status
    assert n20[pd.Timestamp(GAP)] == "no_data" and n20[pd.Timestamp("2025-06-11")] == "ok"
    assert a.acq_date.min() == pd.Timestamp("2025-01-01") and a.acq_date.max() == pd.Timestamp("2026-01-31")
    assert not a.duplicated(["sensor", "acq_date"]).any()


def test_region_table_and_n20_climatology(setup):
    cfg, zips, first, second = setup
    r = pd.read_feather(cfg.processed_dir / "archive" / "region_daily.feather")
    assert set(pd.to_datetime(r.acq_date).dt.year) == {2025, 2026}
    assert set(r.cell_lat.round(1)) <= {35.0, -25.0, 15.0, 5.0, -35.0}
    clim = pd.read_feather(cfg.processed_dir / "archive" / "n20_week_climatology.feather")
    assert np.allclose(clim.p_years, 1 / 7)               # fire in 1 of the 7 climatology years (2019-2025)
    assert set(clim.week) == set(range(52))


def test_archive_overlapping_data_raw_is_refused(setup, tmp_path):
    cfg, zips, first, second = setup
    bad = tmp_path / "zips"
    bad.mkdir()
    write_zip(bad / "DL_FIRE_J1V-C2_3.zip", "fire_archive_J1V-C2_3.csv",
              csv_rows(pd.date_range("2025-12-30", "2026-01-02"), "N20", "VIIRS", "n", "2"))
    with pytest.raises(AssertionError, match="data/raw starts"):
        archive.run(cfg, bad, workers=1)
