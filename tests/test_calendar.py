"""Seam 3: the calendar API contract, on a synthetic sensor grid (two full ISO weeks of 2026)."""
import numpy as np
import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from godseye.api import calendar as calendar_api
from godseye.calendar.store import CalendarStore, fold, grid_cells
from godseye.config import load_config

SENSORS = list(load_config(env={}).sensors)
DAYS = pd.date_range("2026-01-05", "2026-01-18")  # Mon of ISO week 2 .. Sun of ISO week 3


def synthetic_store() -> CalendarStore:
    rows = []
    for d in DAYS:
        rows.append(("Aqua-MODIS", d, 31.875, 35.875, 2, 1))       # Jordan cell: 1 fire cell, 2 detections
        rows.append(("NOAA-20-VIIRS", d, 31.875, 35.875, 9, 4))    # same cell seen by VIIRS: never added to Aqua
        rows.append(("S-NPP-VIIRS", d, 31.875, 35.875, 8, 3))
        rows.append(("NOAA-20-VIIRS", d, -16.375, 179.875, 5, 5))  # Fiji, east of the antimeridian
        rows.append(("NOAA-20-VIIRS", d, -16.375, -179.875, 7, 7))  # west of it
    grid = pd.DataFrame(rows, columns=["sensor", "acq_date", "cell_lat", "cell_lon", "n_detections", "n_fire_cells"])
    grid["sensor"] = pd.Categorical(grid.sensor, categories=SENSORS)
    status = {s: ["ok"] * len(DAYS) for s in SENSORS}
    status["S-NPP-VIIRS"][2] = "no_data"                 # outage on Wed 2026-01-07
    status["Terra-MODIS"] = ["no_data"] * len(DAYS)      # nothing at all from Terra
    status["NOAA-21-VIIRS"][10] = "partial"              # Fri 2026-01-15
    avail = pd.DataFrame([(s, d, st) for s in SENSORS for d, st in zip(DAYS, status[s])],
                         columns=["sensor", "acq_date", "status"])
    avail["sensor"] = pd.Categorical(avail.sensor, categories=SENSORS)
    return CalendarStore(grid, avail, 0.25)


@pytest.fixture(scope="module")
def client():
    app = FastAPI()
    app.include_router(calendar_api.router)
    calendar_api.STORE["calendar"] = synthetic_store()
    with TestClient(app) as c:
        yield c
    calendar_api.STORE.clear()


def sensor(body, name):
    return next(s for s in body["sensors"] if s["sensor"] == name)


def test_weekly_calendar_shape_and_per_sensor_values(client):
    body = client.get("/api/calendar", params={"aoi": "jordan"}).json()
    assert body["unit"] == "week" and body["metric"] == "cell_days"
    assert body["years"] == [2026] and body["periods"] == 53
    assert body["data_range"] == ["2026-01-05", "2026-01-18"]
    assert [s["sensor"] for s in body["sensors"]] == SENSORS
    aqua, n20 = sensor(body, "Aqua-MODIS"), sensor(body, "NOAA-20-VIIRS")
    assert aqua["values"][0][1:3] == [7, 7] and aqua["coverage"][0][1:3] == ["full", "full"]
    assert n20["values"][0][1:3] == [28, 28]          # VIIRS kept separate, not added to Aqua's 7
    assert aqua["values"][0][0] is None and aqua["coverage"][0][0] == "none"   # ISO week 1: before the data


def test_outage_day_makes_the_week_partial_and_is_not_counted_as_zero(client):
    snpp = sensor(client.get("/api/calendar", params={"aoi": "jordan"}).json(), "S-NPP-VIIRS")
    assert snpp["coverage"][0][1:3] == ["partial", "full"]
    assert snpp["values"][0][1:3] == [18, 21]        # 6 days with data x 3, then 7 x 3


def test_partial_delivery_day_flags_the_week_but_keeps_its_count():
    store = synthetic_store()
    cal = store.calendar((-180, -90, 180, 90), "cell_days", "week")
    n21 = store.sensors.index("NOAA-21-VIIRS")
    assert cal.coverage[n21, 0, 2] == "partial"


def test_sensor_with_no_data_is_null_everywhere(client):
    terra = sensor(client.get("/api/calendar", params={"aoi": "jordan"}).json(), "Terra-MODIS")
    assert all(v is None for v in terra["values"][0])
    assert set(terra["coverage"][0]) == {"none"}


def test_detections_metric_and_day_unit(client):
    body = client.get("/api/calendar", params={"aoi": "jordan", "unit": "day", "metric": "detections"}).json()
    assert body["periods"] == 366 and len(sensor(body, "Aqua-MODIS")["values"][0]) == 366
    aqua = sensor(body, "Aqua-MODIS")
    assert aqua["values"][0][4] == 2 and aqua["coverage"][0][4] == "full"    # 2026-01-05 is day 5
    assert aqua["values"][0][3] is None                                     # 2026-01-04: before the data


def test_bbox_across_the_antimeridian(client):
    body = client.get("/api/calendar", params={"bbox": "179.5,-17,-179.5,-16"}).json()
    assert body["aoi"]["name"] is None and body["aoi"]["cells"] == 16   # 4 lat x (2 + 2) lon centres
    assert body["aoi"]["grid_bbox"] == [179.5, -17.0, -179.5, -16.0]
    assert sensor(body, "NOAA-20-VIIRS")["values"][0][1] == 7 * (5 + 7)
    assert sensor(body, "Aqua-MODIS")["values"][0][1] == 0                  # data, but no fire: a real zero


def test_snapped_bbox_and_cell_count():
    cells, snapped = grid_cells((35.0, 31.0, 36.0, 32.0), 0.25)
    assert cells == 16 and snapped == [35.0, 31.0, 36.0, 32.0]
    assert grid_cells((35.01, 31.01, 35.02, 31.02), 0.25) == (0, None)


@pytest.mark.parametrize("params, status", [
    ({}, 422),
    ({"aoi": "jordan", "bbox": "1,2,3,4"}, 422),
    ({"aoi": "atlantis"}, 404),
    ({"bbox": "1,2,3"}, 422),
    ({"bbox": "0,10,5,5"}, 422),
    ({"aoi": "jordan", "unit": "month"}, 422),
    ({"aoi": "jordan", "metric": "frp"}, 422),
])
def test_bad_requests(client, params, status):
    assert client.get("/api/calendar", params=params).status_code == status


def test_named_aois_are_listed(client):
    names = {a["name"] for a in client.get("/api/aois").json()}
    assert {"jordan", "levant", "argentina"} <= names


def test_no_store_is_a_503():
    app = FastAPI()
    app.include_router(calendar_api.router)
    with TestClient(app) as c:
        saved = calendar_api.STORE.pop("calendar", None)
        try:
            assert c.get("/api/calendar", params={"aoi": "jordan"}).status_code == 503
        finally:
            if saved is not None:
                calendar_api.STORE["calendar"] = saved


def test_fold_rejects_unknown_units():
    with pytest.raises(ValueError):
        fold(np.zeros((1, 1)), np.zeros((1, 1), np.int8), pd.date_range("2026-01-01", periods=1), "month")


def test_partial_week_reports_its_data_days(client):
    snpp = sensor(client.get("/api/calendar", params={"aoi": "jordan"}).json(), "S-NPP-VIIRS")
    assert snpp["data_days"][0][1:3] == [6, 7]
    body = client.get("/api/calendar", params={"aoi": "jordan"}).json()
    assert body["period_days"] == 7


def test_periods_that_do_not_exist_are_absent_not_gaps():
    def run(first, last, unit):
        dates = pd.date_range(first, last)
        return fold(np.ones((1, len(dates))), np.zeros((1, len(dates)), np.int8), dates, unit)

    week = run("2024-12-30", "2027-01-03", "week")      # ISO years 2025 (52 weeks) and 2026 (53 weeks), complete
    assert week.years == [2025, 2026]
    assert week.coverage[0, 0, 52] == "absent" and np.isnan(week.values[0, 0, 52])
    assert week.coverage[0, 1, 52] == "full" and week.values[0, 1, 52] == 7
    day = run("2024-01-01", "2025-12-31", "day")        # 2024 is a leap year, 2025 is not
    assert day.coverage[0, 0, 365] == "full" and day.coverage[0, 1, 365] == "absent"


def test_missing_existing_period_is_a_gap_not_absent():
    store = synthetic_store()                            # data 2026-01-05 .. 01-18 only
    week = store.calendar((-180, -90, 180, 90), "cell_days", "week")
    assert (week.coverage[:, 0, 51] == "none").all()     # week 52 exists, no data: a gap
    assert (week.coverage[:, 0, 52] == "none").all()     # 2026 is a 53-week ISO year


@pytest.mark.parametrize("bbox", ["35.01,31.01,35.02,31.02",   # no 0.25° cell centre inside
                                  "40,29,35,33"])               # west > east, not across the antimeridian
def test_unusable_boxes_are_422(client, bbox):
    r = client.get("/api/calendar", params={"bbox": bbox})
    assert r.status_code == 422


def test_antimeridian_box_with_centres_on_one_side_only():
    cells, snapped = grid_cells((179.9, -1, -179.6, 1), 0.25)
    assert cells == 16 and snapped == [-180.0, -1.0, -179.5, 1.0]   # 8 lat x 2 lon centres, all east
