import json
from datetime import date

import numpy as np
import pandas as pd
import pytest

from godseye.cli import main
from godseye.config import Sensor, load_config
from godseye.ingest.aggregate import availability, fire_cells, sensor_grid
from godseye.ingest.manifest import build_manifest

SENSORS = load_config(env={}).sensors


def detections(rows):
    return pd.DataFrame(rows, columns=["satellite", "acq_date", "latitude", "longitude", "frp_mw", "daynight"])


def test_two_detections_in_one_fine_cell_are_one_fire_cell_day():
    det = detections([("Aqua", "2026-07-01", 31.951, 35.931, 5.0, "D"),
                      ("Aqua", "2026-07-01", 31.959, 35.939, 7.0, "N")])
    cells = fire_cells(det, SENSORS, 0.01)
    assert len(cells) == 1
    assert cells.n_detections.item() == 2 and cells.n_detections_daytime.item() == 1
    assert cells.frp_sum_mw.item() == pytest.approx(12.0)


def test_sensors_are_never_summed():
    det = detections([("Aqua", "2026-07-01", 31.951, 35.931, 5.0, "D"),
                      ("NOAA-20", "2026-07-01", 31.951, 35.931, 1.0, "D"),
                      ("Suomi-NPP", "2026-07-01", 31.951, 35.931, 1.0, "D")])
    cells = fire_cells(det, SENSORS, 0.01)
    assert sorted(cells.sensor.astype(str)) == ["Aqua-MODIS", "NOAA-20-VIIRS", "S-NPP-VIIRS"]
    assert (cells.n_detections == 1).all()


def test_unknown_satellite_is_an_error():
    with pytest.raises(ValueError, match="no sensor"):
        fire_cells(detections([("Landsat", "2026-07-01", 0.0, 0.0, 1.0, "D")]), SENSORS, 0.01)


def test_grid_counts_distinct_fine_cells_inside_each_coarse_cell():
    det = detections([("NOAA-20", "2026-07-01", 31.951, 35.931, 1.0, "D"),
                      ("NOAA-20", "2026-07-01", 31.952, 35.932, 1.0, "D"),   # same fine cell
                      ("NOAA-20", "2026-07-01", 31.981, 35.961, 1.0, "N"),   # another fine cell, same 0.25° cell
                      ("NOAA-20", "2026-07-01", 32.301, 35.931, 1.0, "D")])  # next 0.25° cell north
    grid = sensor_grid(fire_cells(det, SENSORS, 0.01), 0.01, 0.25)
    first = grid[grid.cell_lat == 31.875].iloc[0]
    assert (first.cell_lon, first.n_detections, first.n_fire_cells, first.n_fire_cells_daytime) == (35.875, 3, 2, 1)
    assert grid.n_fire_cells.sum() == 3


def test_grid_cells_for_negative_coordinates():
    det = detections([("Aqua", "2026-07-01", -34.601, -58.381, 1.0, "D")])
    grid = sensor_grid(fire_cells(det, SENSORS, 0.01), 0.01, 0.25)
    assert (grid.cell_lat.item(), grid.cell_lon.item()) == (-34.625, -58.375)


def test_availability_flags_outages_partial_days_and_retired_sensors():
    sensors = {"S-NPP-VIIRS": Sensor("S-NPP-VIIRS", "Suomi-NPP", "VIIRS", None, date(2026, 1, 20))}
    days = pd.date_range("2026-01-01", "2026-01-25").to_numpy().astype("datetime64[D]")
    n = np.full(len(days), 100)
    n[9] = 0    # outage on Jan 10
    n[14] = 5   # partial on Jan 15
    cells = pd.DataFrame({"sensor": pd.Categorical(["S-NPP-VIIRS"] * len(days)), "acq_date": days,
                          "n_detections": n})
    cells = cells[cells.n_detections > 0]   # zero days have no fire cells at all
    a = availability(cells, sensors, partial_fraction=0.2).set_index("acq_date").status.astype(str)
    assert a[np.datetime64("2026-01-10")] == "no_data"
    assert a[np.datetime64("2026-01-15")] == "partial"
    assert a[np.datetime64("2026-01-20")] == "ok"
    assert (a[a.index > np.datetime64("2026-01-20")] == "not_operational").all()
    assert (a == "ok").sum() == 18


def test_manifest_is_idempotent_and_describes_each_file(fixture_dir, tmp_path):
    root = fixture_dir.parents[2]
    first = build_manifest([fixture_dir], root)
    again = build_manifest([fixture_dir], root, previous=json.loads(json.dumps(first)))
    assert first == again
    snpp = next(f for f in first["files"] if f["path"].endswith("fire_nrt_SV-C2_fixture.csv"))
    assert snpp["rows"] == 200 and snpp["product"] == ["nrt"] and snpp["satellites"] == {"SNPP": 200}
    assert snpp["first_date"] <= snpp["last_date"] and len(snpp["sha256"]) == 64


def test_aggregate_cli_on_the_cleaned_fixture(fixture_dir, tmp_path):
    main(["clean", str(fixture_dir), "--out", str(tmp_path)])
    main(["aggregate", "--clean-dir", str(tmp_path), "--out", str(tmp_path),
          "--figure", str(tmp_path / "coverage.png")])
    clean = pd.read_feather(tmp_path / "fires_clean.feather")
    cells = pd.read_feather(tmp_path / "sensor_fire_cells.feather")
    grid = pd.read_feather(tmp_path / "sensor_grid_daily.feather")
    avail = pd.read_feather(tmp_path / "sensor_availability.feather")
    assert cells.n_detections.sum() == grid.n_detections.sum() == len(clean)
    assert grid.n_fire_cells.sum() == len(cells)
    assert set(avail.sensor.astype(str)) == set(SENSORS)
    assert (tmp_path / "coverage.png").stat().st_size > 0


def test_exact_cell_boundaries_stay_in_their_own_cell():
    # Plain floor(lat / 0.01) puts -81.79 in cell -8180 because -81.79 / 0.01 = -8178.999...
    det = detections([("Aqua", "2026-07-01", -81.79, -0.07, 1.0, "D"),
                      ("Aqua", "2026-07-01", 0.29, 35.93, 1.0, "D")])
    cells = fire_cells(det, SENSORS, 0.01)
    assert sorted(zip(cells.lat_i, cells.lon_i)) == [(-8179, -7), (29, 3593)]


def test_sensor_without_a_start_date_is_operational_from_its_first_data_day():
    sensors = {"NOAA-20-VIIRS": Sensor("NOAA-20-VIIRS", "NOAA-20", "VIIRS", None, None)}
    days = pd.date_range("2026-01-05", "2026-01-10").to_numpy().astype("datetime64[D]")
    cells = pd.DataFrame({"sensor": pd.Categorical(["NOAA-20-VIIRS"] * len(days)), "acq_date": days,
                          "n_detections": 50})
    a = availability(cells, sensors, 0.2, first=pd.Timestamp("2026-01-01")).set_index("acq_date")
    assert (a.status.astype(str)[:4] == "not_operational").all()
    assert (a.status.astype(str)[4:] == "ok").all()
    assert a.is_coverage_gap.tolist() == [True] * 4 + [False] * 6


def test_aggregate_is_idempotent(fixture_dir, tmp_path):
    main(["clean", str(fixture_dir), "--out", str(tmp_path)])
    for run in ("a", "b"):
        main(["aggregate", "--clean-dir", str(tmp_path), "--out", str(tmp_path / run),
              "--figure", str(tmp_path / f"{run}.png")])
    for table in ("sensor_fire_cells", "sensor_grid_daily", "sensor_availability"):
        read = lambda run: pd.read_feather(tmp_path / run / f"{table}.feather")
        pd.testing.assert_frame_equal(read("a"), read("b"))
