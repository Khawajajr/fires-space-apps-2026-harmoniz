"""Seam 3 (calendar API contract): climatology, anomalies and critical-period endpoints on an 8-year synthetic store."""
from dataclasses import replace

import numpy as np
import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from godseye.api import calendar as calendar_api
from godseye.api import climatology as climatology_api
from godseye.calendar.store import CalendarStore
from godseye.config import get_config, load_config

SENSORS = list(load_config(env={}).sensors)


def multi_year_store() -> CalendarStore:
    days = pd.date_range("2018-01-01", "2025-12-31")
    rng = np.random.default_rng(7)
    week = days.isocalendar().week.to_numpy()
    cells = np.where((week >= 20) & (week <= 34), rng.poisson(15, len(days)), rng.poisson(0.05, len(days)))
    cells[(days.year == 2023) & (week == 30)] *= 5                     # one unusual week
    grid = pd.DataFrame({"sensor": "NOAA-20-VIIRS", "acq_date": days, "cell_lat": 31.875, "cell_lon": 35.875,
                         "n_detections": cells, "n_fire_cells": cells})
    grid = grid[grid.n_fire_cells > 0]
    grid["sensor"] = pd.Categorical(grid.sensor, categories=SENSORS)
    avail = pd.DataFrame([(s, d, "ok" if s == "NOAA-20-VIIRS" else "not_operational") for s in SENSORS for d in days],
                         columns=["sensor", "acq_date", "status"])
    avail["sensor"] = pd.Categorical(avail.sensor, categories=SENSORS)
    return CalendarStore(grid, avail, 0.25)


def make_client(activity: str):
    app = FastAPI()
    app.include_router(calendar_api.router)
    app.include_router(climatology_api.router)
    cfg = load_config(env={})
    app.dependency_overrides[get_config] = lambda: replace(cfg, climatology={"activity": activity})
    return TestClient(app)


@pytest.fixture(scope="module")
def client():
    calendar_api.STORE["calendar"] = multi_year_store()
    with make_client("relative") as c:      # the proposed ADR 0006 amendment
        yield c
    calendar_api.STORE.clear()


def test_absolute_activity_lets_background_noise_make_every_week_active():
    """Evidence for the proposed amendment: with ADR 0006 as approved (>= 1 cell-day), stray winter detections
    (about 0.35 cell-days a week here) put every week in season."""
    calendar_api.STORE["calendar"] = multi_year_store()
    try:
        with make_client("absolute") as c:
            b = c.get("/api/calendar/climatology", params=Q).json()
            assert b["activity"] == "absolute" and b["gate_rule"] == "default" and len(b["gated_weeks"]) == 52
            assert b["gate_counts"]["default_rule_weeks"] == 52
            periods = c.get("/api/calendar/critical-periods", params=Q).json()["periods"]
            assert len(periods) == 1 and periods[0]["weeks"] == 52
    finally:
        calendar_api.STORE.clear()


Q = {"aoi": "jordan", "series": "NOAA-20-VIIRS"}


def test_climatology_profile(client):
    b = client.get("/api/calendar/climatology", params=Q).json()
    assert b["status"] == "ok" and b["message"] is None and len(b["history_years"]) == 8
    assert b["activity"] == "relative" and b["gate_counts"]["default_rule_weeks"] < 52
    assert b["gate_rule"] == "default" and len(b["weeks"]) == 52
    w27 = b["weeks"][26]
    assert w27["week"] == 27 and w27["p_active"] == 1.0 and 80 < w27["median"] < 130
    assert b["weeks"][0]["p_active"] < 0.1


def test_critical_period_is_the_summer_season(client):
    b = client.get("/api/calendar/critical-periods", params=Q).json()
    top = b["periods"][0]
    assert top["rank"] == 1 and 18 <= top["start_week"] <= 20 and 34 <= top["end_week"] <= 36
    assert " - " in top["label"]


def test_anomaly_is_the_unusual_week(client):
    b = client.get("/api/calendar/anomalies", params=Q).json()
    first = b["anomalies"][0]
    assert (first["year"], first["week"]) == (2023, 30) and first["week_start"] == "2023-07-24"


def test_harmonized_series_needs_a_chain(client):
    assert client.get("/api/calendar/climatology", params={"aoi": "jordan"}).status_code == 409


def test_bad_series_and_empty_box(client):
    assert client.get("/api/calendar/climatology", params={"aoi": "jordan", "series": "Landsat"}).status_code == 422
    r = client.get("/api/calendar/anomalies", params={"bbox": "35.01,31.01,35.02,31.02", "series": "NOAA-20-VIIRS"})
    assert r.status_code == 422
