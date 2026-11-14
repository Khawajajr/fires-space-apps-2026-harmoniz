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


def multi_year_store(end: str = "2025-12-31", spike_year: int = 2023) -> CalendarStore:
    days = pd.date_range("2018-01-01", end)
    rng = np.random.default_rng(7)
    week = days.isocalendar().week.to_numpy()
    cells = np.where((week >= 20) & (week <= 34), rng.poisson(15, len(days)), rng.poisson(0.05, len(days)))
    cells[(days.year == spike_year) & (week == 30)] *= 5               # one unusual week
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
            crit = c.get("/api/calendar/critical-periods", params=Q).json()
            assert crit["all_year"] and crit["summary"].startswith("Active all year")
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
    assert b["all_year"] is False and b["summary"] is None


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


def test_this_week_vs_history_on_an_unusual_current_week():
    calendar_api.STORE["calendar"] = multi_year_store(end="2025-07-27", spike_year=2025)   # ends with ISO week 30
    try:
        with make_client("relative") as c:
            b = c.get("/api/calendar/now", params=Q).json()
    finally:
        calendar_api.STORE.clear()
    assert b["status"] == "ok" and (b["year"], b["week"]) == (2025, 30)
    assert b["level"] == "unusually high" and b["percentile"] >= 90 and b["in_season"] is True
    assert b["reference_years"] == 7 and "Week 30" in b["summary"] and "unusually high" in b["summary"]
    assert "of 21 values from 7 past years" in b["summary"] and "th percentile" in b["summary"]
    calendar_api.STORE["calendar"] = multi_year_store(end="2025-07-27", spike_year=2025)
    try:
        with make_client("relative") as c:
            first = c.get("/api/calendar/anomalies", params=Q).json()["anomalies"][0]
    finally:
        calendar_api.STORE.clear()
    assert (first["year"], first["week"]) == (2025, 30)      # the incomplete current year still gets anomalies


def test_this_week_vs_history_needs_five_other_years():
    calendar_api.STORE["calendar"] = multi_year_store(end="2021-07-25")
    try:
        with make_client("relative") as c:
            b = c.get("/api/calendar/now", params=Q).json()
    finally:
        calendar_api.STORE.clear()
    assert b["status"] == "insufficient_history" and b["reference_years"] == 3 and b["level"] is None
    assert "currently 3" in b["message"]


def test_level_bands():
    from godseye.api.climatology import level_of
    assert [level_of(p) for p in (95, 80, 50, 20, 5)] == [
        "unusually high", "above usual", "about usual", "below usual", "unusually low"]


def test_ordinals():
    from godseye.api.climatology import ordinal
    assert [ordinal(n) for n in (1, 2, 3, 4, 11, 12, 13, 21, 22, 23, 100)] == [
        "1st", "2nd", "3rd", "4th", "11th", "12th", "13th", "21st", "22nd", "23rd", "100th"]


def test_partial_latest_week_is_flagged_in_the_summary():
    calendar_api.STORE["calendar"] = multi_year_store(end="2025-07-25")   # ISO week 30 has 5 of 7 days
    try:
        with make_client("relative") as c:
            b = c.get("/api/calendar/now", params=Q).json()
    finally:
        calendar_api.STORE.clear()
    assert b["week"] == 30 and b["data_days"] == 5 and "from 5 of 7 days scaled to a full week" in b["summary"]
