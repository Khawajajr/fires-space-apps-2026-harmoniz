"""Calendar endpoints (seam 3: the calendar API contract)."""
from __future__ import annotations

import math
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from godseye.calendar.store import CalendarStore, grid_cells
from godseye.config import AOI, Config, get_config

router = APIRouter(prefix="/api")
STORE: dict = {}

METRIC_LABELS = {"cell_days": "fire cell-days (0.01° cells with ≥1 kept detection)",
                 "detections": "kept detections"}
NOTES = [
    "Each sensor is shown separately; counts from different sensors are never added.",
    "Counts are of kept detections: nominal/high confidence vegetation fires.",
    "null = no data (sensor not operational, outage, or outside the data range), never zero fire.",
    "Partial periods (marked with a bar) count only the days with data; they are never complete totals.",
    "Clouds hide fires and are not mapped: a low count can mean cloud, not absence of fire.",
    "The AOI is the set of 0.25° cells whose centre lies inside the box.",
]


class AOIOut(BaseModel):
    name: str | None = Field(description="named AOI, or null for a drawn bbox")
    label: str
    bbox: list[float] = Field(description="requested [west, south, east, north]")
    grid_bbox: list[float] | None = Field(description="bbox snapped to the 0.25° cells used")
    cells: int = Field(description="number of 0.25° cells in the AOI")


class SensorCalendar(BaseModel):
    sensor: str
    values: list[list[float | None]] = Field(description="[year][period]; null where coverage is none or absent")
    coverage: list[list[Literal["full", "partial", "none", "absent"]]]
    data_days: list[list[int]] = Field(description="[year][period] days with data, out of period_days")


class CalendarResponse(BaseModel):
    aoi: AOIOut
    unit: Literal["week", "day"]
    metric: Literal["cell_days", "detections"]
    metric_label: str
    years: list[int]
    periods: int = Field(description="53 ISO weeks or 366 days of year")
    period_days: int = Field(description="days in a complete period: 7 for weeks, 1 for days")
    data_range: list[str] = Field(description="first and last day of data, YYYY-MM-DD")
    sensors: list[SensorCalendar]
    notes: list[str]


class AOIListItem(BaseModel):
    name: str
    label: str
    bbox: list[float]


def get_store() -> CalendarStore:
    if "calendar" not in STORE:
        raise HTTPException(503, "calendar data not loaded - run `godseye aggregate`")
    return STORE["calendar"]


def resolve_aoi(aoi: str | None, bbox: str | None, cfg: Config) -> AOI:
    if aoi and bbox:
        raise HTTPException(422, "give either aoi or bbox, not both")
    if aoi:
        if aoi not in cfg.aois:
            raise HTTPException(404, f"unknown aoi {aoi!r}; known: {sorted(cfg.aois)}")
        return cfg.aois[aoi]
    if not bbox:
        raise HTTPException(422, "give aoi=<name> or bbox=west,south,east,north")
    try:
        west, south, east, north = map(float, bbox.split(","))
    except ValueError:
        raise HTTPException(422, "bbox must be 'west,south,east,north' in degrees")
    if not (-180 <= west <= 180 and -180 <= east <= 180 and -90 <= south < north <= 90):
        raise HTTPException(422, "bbox out of range: -180..180 longitude, -90..90 latitude, south < north")
    if west > east and not (west > 0 > east):
        raise HTTPException(422, "west > east: swap them, or for a box across the antimeridian give west > 0 > east")
    return AOI(None, "Custom area", (west, south, east, north))


@router.get("/aois", response_model=list[AOIListItem])
def list_aois(cfg: Config = Depends(get_config)):
    return [AOIListItem(name=a.name, label=a.label, bbox=list(a.bbox)) for a in cfg.aois.values()]


@router.get("/calendar", response_model=CalendarResponse)
def calendar(
    aoi: str | None = Query(None, description="named AOI, see /api/aois"),
    bbox: str | None = Query(None, description="west,south,east,north"),
    unit: Literal["week", "day"] = Query("week"),
    metric: Literal["cell_days", "detections"] = Query("cell_days"),
    store: CalendarStore = Depends(get_store),
    cfg: Config = Depends(get_config),
):
    area = resolve_aoi(aoi, bbox, cfg)
    cells, snapped = grid_cells(area.bbox, store.grid_deg)
    if cells == 0:
        raise HTTPException(422, f"the box contains no {store.grid_deg}° grid cell centre; draw a larger box")
    cal = store.calendar(area.bbox, metric, unit)
    clean = lambda v: None if math.isnan(v) else round(float(v), 3)
    return CalendarResponse(
        aoi=AOIOut(name=area.name, label=area.label, bbox=list(area.bbox), grid_bbox=snapped, cells=cells),
        unit=unit, metric=metric, metric_label=METRIC_LABELS[metric], years=cal.years, periods=cal.periods,
        period_days=cal.period_days,
        data_range=[store.first.strftime("%Y-%m-%d"), store.last.strftime("%Y-%m-%d")],
        sensors=[SensorCalendar(sensor=name, values=[[clean(v) for v in row] for row in cal.values[i]],
                                coverage=cal.coverage[i].tolist(), data_days=cal.data_days[i].tolist())
                 for i, name in enumerate(store.sensors)],
        notes=NOTES,
    )
