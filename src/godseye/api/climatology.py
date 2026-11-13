"""Climatology, anomaly and critical-period endpoints over one AOI's weekly series (ADR 0006)."""
from __future__ import annotations

from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from godseye.api.calendar import AOIOut, get_store, resolve_aoi
from godseye.calendar import climatology as C
from godseye.calendar.store import CalendarStore, grid_cells
from godseye.config import Config, get_config

router = APIRouter(prefix="/api/calendar")
REFERENCE_YEAR = 2025      # a 52-week ISO year, only for turning week numbers into readable dates


def week_label(week: int) -> str:
    return day_month(date.fromisocalendar(REFERENCE_YEAR, week, 1))


class Common(BaseModel):
    aoi: AOIOut
    series: str = Field(description="'harmonized' (the headline) or a sensor name")
    series_label: str
    status: Literal["ok", "insufficient_history"]
    message: str | None = Field(description="why a panel is empty, in plain language")
    years: list[int]
    history_years: list[int] = Field(description=f"years with >= {C.MIN_YEAR_SHARE:.0%} of weeks usable")
    min_years: int = C.MIN_YEARS
    gate_rule: Literal["default", "relative", "floor"] | None
    gated_weeks: list[int]
    notes: list[str]


class ClimWeek(BaseModel):
    week: int
    week_start: str = Field(description="approximate start date of the ISO week")
    median: float | None
    p10: float | None
    p90: float | None
    p_active: float | None = Field(description="share of past values counted as active (see active_threshold)")
    n: int


class ClimatologyResponse(Common):
    mean_weekly: float | None = Field(description="mean weekly value over the whole record, in the series' units")
    active_threshold: float | None = Field(description="weekly value that counts as 'active' for this AOI")
    activity: str = Field(description="'absolute' (ADR 0006) or 'relative' (proposed amendment)")
    gate_counts: dict = Field(description="weeks passing each gate rule, for the ingest report")
    weeks: list[ClimWeek]


class Anomaly(BaseModel):
    year: int
    week: int
    week_start: str
    value: float
    median: float
    p90: float
    z: float | None


class AnomaliesResponse(Common):
    anomalies: list[Anomaly]


class Period(BaseModel):
    rank: int
    start_week: int
    end_week: int
    label: str = Field(description="approximate dates, e.g. '12 May - 1 Sep'")
    weeks: int
    peak_week: int
    expected_activity: float = Field(description="sum of the weekly medians in the period")
    share_of_year: float
    mean_p_active: float


class CriticalPeriodsResponse(Common):
    periods: list[Period]


def notes(activity: str, series: str) -> list[str]:
    active = (f"A week counts as active when it reaches {C.ACTIVE_SHARE:.0%} of this area's peak weekly median "
              f"(never below {C.ACTIVE:g}); proposed amendment to ADR 0006." if activity == "relative" else
              f"A week counts as active with at least {C.ACTIVE:g} fire cell-day (ADR 0006).")
    out = [f"Climatology uses only past weeks with full data (or >= {C.MIN_PARTIAL_DAYS} of 7 days, scaled up).",
           f"Each ISO week pools the weeks either side (+-{C.POOL}) to steady estimates from few years.", active,
           "Anomalies compare each year with a climatology built without that year.",
           "Rules for the activity gate were fixed before looking at any data (ADR 0006)."]
    if series != "harmonized":
        out.append("One sensor's raw series: the gate's floor is applied in its own units, not Aqua-equivalent.")
    return out


def day_month(d: date) -> str:
    return d.strftime("%d %b").lstrip("0")


def analysis(aoi: str | None, bbox: str | None, series: str, store: CalendarStore, cfg: Config):
    area = resolve_aoi(aoi, bbox, cfg)
    cells, snapped = grid_cells(area.bbox, store.grid_deg)
    if cells == 0:
        raise HTTPException(422, f"the box contains no {store.grid_deg}° grid cell centre; draw a larger box")
    if series == "harmonized":
        h = store.harmonized(area.bbox, "week")
        if h is None:
            raise HTTPException(409, "no harmonized series yet - run `godseye harmonize`, or pass series=<sensor>")
        values, coverage, days, label = h.values, h.coverage, h.data_days, store.chain.label
        years = store.calendar(area.bbox, "cell_days", "week").years
    elif series in store.sensors:
        cal = store.calendar(area.bbox, "cell_days", "week")
        i = store.sensors.index(series)
        values, coverage, days, label, years = cal.values[i], cal.coverage[i], cal.data_days[i], series, cal.years
    else:
        raise HTTPException(422, f"series must be 'harmonized' or one of {store.sensors}")
    activity = cfg.climatology["activity"]
    a = C.analyse(years, values, coverage, days, activity)
    common = dict(aoi=AOIOut(name=area.name, label=area.label, bbox=list(area.bbox), grid_bbox=snapped, cells=cells),
                  series=series, series_label=label, status=a.status, message=a.message, years=a.years,
                  history_years=a.history_years, gate_rule=a.gate_rule, gated_weeks=a.gated_weeks,
                  notes=notes(activity, series))
    return a, common


Series = Query("harmonized", description="'harmonized' (default) or a sensor name")


@router.get("/climatology", response_model=ClimatologyResponse)
def climatology(aoi: str | None = None, bbox: str | None = None, series: str = Series,
                store: CalendarStore = Depends(get_store), cfg: Config = Depends(get_config)):
    a, common = analysis(aoi, bbox, series, store, cfg)
    return ClimatologyResponse(**common, mean_weekly=a.mean_weekly, active_threshold=a.active_threshold,
                               activity=a.activity, gate_counts=a.gate_counts,
                               weeks=[ClimWeek(**c, week_start=week_label(c["week"])) for c in a.climatology])


@router.get("/anomalies", response_model=AnomaliesResponse)
def anomalies(aoi: str | None = None, bbox: str | None = None, series: str = Series,
              store: CalendarStore = Depends(get_store), cfg: Config = Depends(get_config)):
    a, common = analysis(aoi, bbox, series, store, cfg)
    return AnomaliesResponse(**common, anomalies=[
        Anomaly(**x, week_start=date.fromisocalendar(x["year"], min(x["week"], 52), 1).isoformat())
        for x in a.anomalies])


@router.get("/critical-periods", response_model=CriticalPeriodsResponse)
def critical_periods(aoi: str | None = None, bbox: str | None = None, series: str = Series,
                     store: CalendarStore = Depends(get_store), cfg: Config = Depends(get_config)):
    a, common = analysis(aoi, bbox, series, store, cfg)
    return CriticalPeriodsResponse(**common, periods=[
        Period(**p, label=f"{week_label(p['start_week'])} - "
                          f"{day_month(date.fromisocalendar(REFERENCE_YEAR, p['end_week'], 7))}")
        for p in a.critical_periods])
