"""Climatology, anomaly and critical-period endpoints over one AOI's weekly series (ADR 0006)."""
from __future__ import annotations

from dataclasses import replace
from datetime import date
from typing import Literal

import numpy as np
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from godseye.api.calendar import (
    AOIOut,
    aoi_label,
    get_store,
    headline_label,
    pick_store,
    resolve_aoi,
    too_large_message,
)
from godseye.calendar import climatology as C
from godseye.calendar.store import CalendarStore, grid_cells
from godseye.config import Config, get_config
from godseye.i18n import Lang, t

router = APIRouter(prefix="/api/calendar")
REFERENCE_YEAR = 2025      # a 52-week ISO year, only for turning week numbers into readable dates


def week_label(week: int, lang: str = "en") -> str:
    return day_month(date.fromisocalendar(REFERENCE_YEAR, week, 1), lang)


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
    all_year: bool = Field(False, description="every week of the year passes the activity gate")
    summary: str | None = Field(None, description="plain-language reading of the periods (e.g. active all year)")


def notes(activity: str, series: str, lang: str = "en") -> list[str]:
    active = (t(lang, "api.clim_note.active_relative", share=f"{C.ACTIVE_SHARE:.0%}", min=f"{C.ACTIVE:g}")
              if activity == "relative" else t(lang, "api.clim_note.active_absolute", min=f"{C.ACTIVE:g}"))
    out = [t(lang, "api.clim_note.partial", days=C.MIN_PARTIAL_DAYS), t(lang, "api.clim_note.pool", pool=C.POOL),
           active, t(lang, "api.clim_note.loo"), t(lang, "api.clim_note.fixed")]
    if series != "harmonized":
        out.append(t(lang, "api.clim_note.raw_floor"))
    return out


def day_month(d: date, lang: str = "en") -> str:
    return f"{d.day} {t(lang, f'api.month.{d.month}')}"


def _series(area, series: str, store: CalendarStore) -> dict:
    """The weekly series (values, coverage, data_days, years; lo/hi for the harmonized one), or an HTTP error."""
    if series == "harmonized":
        h = store.harmonized(area.bbox, "week")
        if h is None:
            raise HTTPException(409, "no harmonized series yet - run `godseye harmonize`, or pass series=<sensor>")
        return dict(values=h.values, coverage=h.coverage, days=h.data_days, years=h.years, lo=h.lo, hi=h.hi)
    if series in store.sensors:
        cal = store.calendar(area.bbox, "cell_days", "week")
        i = store.sensors.index(series)
        return dict(values=cal.values[i], coverage=cal.coverage[i], days=cal.data_days[i], years=cal.years)
    raise HTTPException(422, f"series must be 'harmonized' or one of {store.sensors}")


def analysis(aoi: str | None, bbox: str | None, series: str, store: CalendarStore, cfg: Config, lang: str = "en"):
    """(Analysis, common response fields, the series itself) for one AOI and series."""
    area = resolve_aoi(aoi, bbox, cfg)
    store = pick_store(store, area.bbox)
    cells, snapped = grid_cells(area.bbox, store.grid_deg)
    if cells == 0:
        raise HTTPException(422, f"the box contains no {store.grid_deg}° grid cell centre; draw a larger box")
    ser = _series(area, series, store)
    values, coverage, days, years = ser["values"], ser["coverage"], ser["days"], ser["years"]
    label = headline_label(store.chain, lang) if series == "harmonized" else series
    activity = cfg.climatology["activity"]
    a = C.analyse(years, values, coverage, days, activity)
    if a.status == "insufficient_history":
        a = replace(a, message=too_large_message(area.bbox, lang) or
                    t(lang, "api.needs_history", min=C.MIN_YEARS, n=len(a.history_years)))
    elif a.gate_rule == "floor":
        a = replace(a, message=t(lang, "api.floor"))
    common = dict(aoi=AOIOut(name=area.name, label=aoi_label(area, lang), bbox=list(area.bbox), grid_bbox=snapped,
                             cells=cells),
                  series=series, series_label=label, status=a.status, message=a.message, years=a.years,
                  history_years=a.history_years, gate_rule=a.gate_rule, gated_weeks=a.gated_weeks,
                  notes=notes(activity, series, lang))
    return a, common, ser


Series = Query("harmonized", description="'harmonized' (default) or a sensor name")
LangQ = Query("en", description="language of labels and messages: en (default) or ar")


@router.get("/climatology", response_model=ClimatologyResponse)
def climatology(aoi: str | None = None, bbox: str | None = None, series: str = Series, lang: Lang = LangQ,
                store: CalendarStore = Depends(get_store), cfg: Config = Depends(get_config)):
    a, common, _ = analysis(aoi, bbox, series, store, cfg, lang)
    return ClimatologyResponse(**common, mean_weekly=a.mean_weekly, active_threshold=a.active_threshold,
                               activity=a.activity, gate_counts=a.gate_counts,
                               weeks=[ClimWeek(**c, week_start=week_label(c["week"], lang)) for c in a.climatology])


@router.get("/anomalies", response_model=AnomaliesResponse)
def anomalies(aoi: str | None = None, bbox: str | None = None, series: str = Series, lang: Lang = LangQ,
              store: CalendarStore = Depends(get_store), cfg: Config = Depends(get_config)):
    a, common, _ = analysis(aoi, bbox, series, store, cfg, lang)
    return AnomaliesResponse(**common, anomalies=[
        Anomaly(**x, week_start=date.fromisocalendar(x["year"], min(x["week"], 52), 1).isoformat())
        for x in a.anomalies])


@router.get("/critical-periods", response_model=CriticalPeriodsResponse)
def critical_periods(aoi: str | None = None, bbox: str | None = None, series: str = Series, lang: Lang = LangQ,
                     store: CalendarStore = Depends(get_store), cfg: Config = Depends(get_config)):
    a, common, _ = analysis(aoi, bbox, series, store, cfg, lang)
    periods = [Period(**p, label=f"{week_label(p['start_week'], lang)} - "
                                 f"{day_month(date.fromisocalendar(REFERENCE_YEAR, p['end_week'], 7), lang)}")
               for p in a.critical_periods]
    all_year = any(p.weeks >= 52 for p in periods)
    return CriticalPeriodsResponse(**common, periods=periods, all_year=all_year,
                                   summary=t(lang, "api.all_year", peak=periods[0].peak_week) if all_year else None)


class NowResponse(BaseModel):
    aoi: AOIOut
    series: str
    series_label: str
    status: Literal["ok", "insufficient_history", "no_recent_data"]
    message: str | None
    year: int | None
    week: int | None
    week_start: str | None
    week_end: str | None
    value: float | None = Field(description="this week's value (partial weeks scaled to 7 days, as in the climatology)")
    lo: float | None = Field(None, description="90% band of a harmonized estimate (scaled like the value)")
    hi: float | None = None
    data_days: int | None
    data_age_days: int | None = Field(None, description="days from the last day with data in this week to today")
    reference_years: int = Field(description="other history years contributing to the reference")
    reference_values: int = Field(0, description="values in the reference (the week and its neighbours)")
    median: float | None
    p10: float | None
    p90: float | None
    percentile: float | None = Field(description="share of past values at or below this week's (0-100)")
    in_season: bool | None
    level: Literal["unusually low", "below usual", "about usual", "above usual", "unusually high"] | None
    summary: str | None = Field(description="one plain-language sentence")


def ordinal(n: int) -> str:
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


STALE_DAYS = 14


def level_of(percentile: float) -> str:
    if percentile >= 90:
        return "unusually high"
    if percentile >= 75:
        return "above usual"
    if percentile > 25:
        return "about usual"
    if percentile > 10:
        return "below usual"
    return "unusually low"


@router.get("/now", response_model=NowResponse)
def now(aoi: str | None = None, bbox: str | None = None, series: str = Series, lang: Lang = LangQ,
        store: CalendarStore = Depends(get_store), cfg: Config = Depends(get_config)):
    """The latest week with enough data, against the same ISO week (+-1) in the other history years."""
    a, common, ser = analysis(aoi, bbox, series, store, cfg, lang)
    base = {k: common[k] for k in ("aoi", "series", "series_label")}
    values, coverage, days, years = ser["values"], ser["coverage"], ser["days"], ser["years"]
    u = C.usable(values, coverage, days)
    latest = [(yi, w) for yi in range(len(years)) for w in range(u.shape[1]) if not np.isnan(u[yi, w])]
    empty = dict(year=None, week=None, week_start=None, week_end=None, value=None, data_days=None, reference_years=0,
                 median=None, p10=None, p90=None, percentile=None, in_season=None, level=None, summary=None)
    if not latest:
        return NowResponse(**base, **empty, status="no_recent_data", message=t(lang, "api.no_recent"))
    yi, w = latest[-1]
    year, week, v, n_days = years[yi], w + 1, float(u[yi, w]), int(days[yi][w])
    scale = 7.0 / n_days if coverage[yi][w] == "partial" else 1.0
    start, end = date.fromisocalendar(year, week, 1), date.fromisocalendar(year, week, 7)
    area = resolve_aoi(aoi, bbox, cfg)
    last = pick_store(store, area.bbox).last.date()
    age = max(0, (date.today() - min(end, last)).days)       # from the week's last day with data
    band = {}
    if "lo" in ser and not np.isnan(ser["lo"][yi][w]):
        band = dict(lo=round(float(ser["lo"][yi][w]) * scale, 2), hi=round(float(ser["hi"][yi][w]) * scale, 2))
    ref, ref_years = C.week_reference(years, values, coverage, days, week,
                                      [y for y in a.history_years if y != year])
    info = dict(year=year, week=week, week_start=start.isoformat(), week_end=end.isoformat(), value=round(v, 2),
                data_days=n_days, data_age_days=age, reference_years=ref_years, reference_values=int(len(ref)), **band)
    if ref_years < C.MIN_YEARS:
        return NowResponse(**base, **{**empty, **info}, status="insufficient_history",
                           message=too_large_message(area.bbox, lang) or
                           t(lang, "api.needs_history_now", min=C.MIN_YEARS, n=ref_years))
    pct = C.percentile_of(v, ref)
    lvl = level_of(pct)
    in_season = a.status == "ok" and min(week, C.WEEKS) in a.gated_weeks
    unit = (t(lang, "api.now.unit_harmonized") if series == "harmonized"
            else t(lang, "api.now.unit_sensor", sensor=series))
    est = t(lang, "api.now.band", lo=f"{band['lo']:.0f}", hi=f"{band['hi']:.0f}") if band else ""
    partial = t(lang, "api.now.partial", n=n_days) if scale != 1.0 else ""
    stale = t(lang, "api.now.stale", age=age) if age > STALE_DAYS else ""
    summary = t(lang, "api.now.summary", week=week, day=day_month(start, lang), value=f"{v:.0f}", unit=unit, band=est,
                partial=partial, level=t(lang, f"api.level.{lvl}"),
                pct=ordinal(round(pct)) if lang == "en" else round(pct), n=len(ref), years=ref_years,
                season=t(lang, "api.now.in_season" if in_season else "api.now.out_season"), stale=stale)
    return NowResponse(**base, **info, status="ok", message=None, median=float(np.median(ref)),
                       p10=float(np.quantile(ref, 0.1)), p90=float(np.quantile(ref, 0.9)), percentile=round(pct, 1),
                       in_season=in_season, level=lvl, summary=summary)
