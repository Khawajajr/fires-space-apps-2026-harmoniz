"""Ticket 07 (rescoped): one pass over archive zips -> AOI stores, calibration regions, availability, climatology."""
import json
import zipfile
from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from godseye.calendar.tiles import TileStores, tiles_for
from godseye.config import load_config
from godseye.ingest import archive
from godseye.ingest.aggregate import availability, sensor_grid

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
    sensor_grid(cells, 0.01, 0.25).to_feather(cfg.processed_dir / "sensor_grid_daily.feather")
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


def tile_stores(cfg, **kw):
    avail = pd.read_feather(cfg.processed_dir / "archive" / "sensor_availability.feather")
    return TileStores(cfg.processed_dir / "archive" / "tiles", avail, 0.25, **kw)


def test_global_tiles_give_any_box_the_multi_year_calendar(setup):
    cfg, zips, first, second = setup
    report = json.loads((cfg.processed_dir / "archive" / "ingest_report.json").read_text())
    assert report["tiles"]["files"] == 3                     # Jordan (both spots and 2026), Argentina, elsewhere
    t = tile_stores(cfg)
    store = t.store_for((19.0, 9.0, 22.0, 12.0))            # around the "elsewhere" spot, outside every named AOI
    cal = store.calendar((19.0, 9.0, 22.0, 12.0), "cell_days", "week")
    assert cal.years[0] == 2025 and cal.years[-1] == 2026
    n20 = cal.values[store.sensors.index("NOAA-20-VIIRS")]
    assert np.nansum(n20[0]) == 361      # one fire cell-day a day: ISO 2025 = 1 Jan..28 Dec (362 days) minus the gap
    assert t.store_for((19.0, 9.0, 22.0, 12.0)) is store     # cached


def test_a_fire_free_box_reads_zero_not_missing_and_huge_boxes_are_refused(setup):
    cfg, zips, first, second = setup
    t = tile_stores(cfg, max_rows=10)
    quiet = t.store_for((100.0, 40.0, 101.0, 41.0))
    cal = quiet.calendar((100.0, 40.0, 101.0, 41.0), "cell_days", "week")
    aqua = cal.values[quiet.sensors.index("Aqua-MODIS")]
    assert np.nanmax(aqua) == 0 and not np.isnan(aqua[0, 1])   # Aqua delivered, saw nothing: 0
    assert t.store_for((-80.0, -50.0, -50.0, -20.0)) is None    # more rows than max_rows: caller falls back


def test_tiles_for_handles_the_antimeridian():
    assert tiles_for((170.0, -20.0, -170.0, -10.0)) == ["t_-20_+170", "t_-20_-180"]
    assert tiles_for((34.0, 29.0, 42.5, 37.5)) == ["t_+20_+030", "t_+20_+040", "t_+30_+030", "t_+30_+040"]


def test_api_serves_any_box_from_the_tiles_and_explains_a_box_that_is_too_large(setup):
    from dataclasses import replace

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from godseye.api import calendar as calendar_api
    from godseye.api import climatology as climatology_api
    from godseye.calendar.store import CalendarStore
    from godseye.config import get_config

    cfg, zips, first, second = setup
    proc = cfg.processed_dir
    calendar_api.STORE["calendar"] = CalendarStore(pd.read_feather(proc / "sensor_grid_daily.feather"),
                                                   pd.read_feather(proc / "sensor_availability.feather"), 0.25)
    calendar_api.STORE["tiles"] = tile_stores(cfg, max_rows=2000)        # small box ~1,100 rows; big ~3,300
    app = FastAPI()
    app.include_router(calendar_api.router)
    app.include_router(climatology_api.router)
    app.dependency_overrides[get_config] = lambda: replace(cfg, climatology={"activity": "relative"})
    try:
        with TestClient(app) as c:
            small = c.get("/api/calendar", params={"bbox": "19,9,22,12", "unit": "week"}).json()
            assert small["years"][0] == 2025                       # from the tiles, not the 2026-only global store
            big = c.get("/api/calendar/now", params={"bbox": "-80,-50,40,40", "series": "NOAA-20-VIIRS"}).json()
            assert big["status"] == "insufficient_history" and "too large" in big["message"]
    finally:
        calendar_api.STORE.clear()


def test_country_files_drop_cells_our_modis_downloads_flag_as_static_sources(tmp_path):
    """MODIS 2000-2011 comes from the FIRMS yearly summaries by country (one CSV per country, newer static-source
    flag): fire cell-days in a cell our own MODIS downloads mark as a static land source (type 2) are dropped."""
    cfg = load_config(env={"GODSEYE_DATA_DIR": str(tmp_path / "data")})
    days = pd.date_range("2010-03-01", "2010-03-10")
    download = tmp_path / "DL_FIRE_M-C61_9.zip"
    static_row = f"{SPOTS[0][0]},{SPOTS[0][1]},330,1,1,2015-01-01,1030,Aqua,MODIS,80,6.03,290,5.5,D,2"
    write_zip(download, "fire_archive_M-C61_9.csv", f"{HEADER}\n{static_row}\n")
    country = tmp_path / "modis_2010_all_countries.zip"
    rows = csv_rows(days, "Aqua", "MODIS", 80, "6.2").split("\n")
    with zipfile.ZipFile(country, "w") as z:                  # Jordan's rows in one file, the rest in another
        z.writestr("modis/2010/modis_2010_Jordan.csv", "\n".join([HEADER] + [r for r in rows[1:] if r.startswith(
            ("32.0012", "31.5"))]) + "\n")
        z.writestr("modis/2010/modis_2010_Other.csv", "\n".join([HEADER] + [r for r in rows[1:] if r and not
                   r.startswith(("32.0012", "31.5"))]) + "\n")
    assert archive.is_country_zip(country) and not archive.is_country_zip(download)
    static = archive.static_mask([download], tmp_path / "mask.feather", 0.01, 1000, 1)
    assert len(static) == 1
    assert archive.static_mask([download], tmp_path / "mask.feather", 0.01, 1000, 1).tolist() == static.tolist()
    meta = archive.process_zip(str(country), str(tmp_path / "parts"), "c", **archive.worker_args(cfg), static=static)
    assert meta["filters"]["dropped_cell_days_static_source_mask"] == len(days)
    levant = pd.read_feather(tmp_path / "parts" / "c" / "aoi_levant.feather")
    assert len(levant) == len(days)                           # only the second Jordan spot is left
    assert meta["rows"] == len(days) * 5 and meta["first_date"] == "2010-03-01"
    entry = archive.manifest_entry(country, "c", meta, tmp_path)
    assert entry["source"]["url"].endswith("/data/country/zips/modis_2010_all_countries.zip")
