"""Calendar endpoints (seam 3: the calendar API contract)."""
from __future__ import annotations

import math
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from godseye.calendar.store import CalendarStore, grid_cells
from godseye.config import AOI, Config, get_config
from godseye.harmonize.link import display_method

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
    note: str | None = Field(None, description="why this sensor's series is not directly comparable, if it isn't")
    values: list[list[float | None]] = Field(description="[year][period]; null where coverage is none or absent")
    coverage: list[list[Literal["full", "partial", "none", "absent"]]]
    data_days: list[list[int]] = Field(description="[year][period] days with data, out of period_days")


class HarmonizedOut(BaseModel):
    label: str = Field(description="e.g. Aqua-MODIS-equivalent (afternoon overpass)")
    target: str
    provisional: bool = Field(description="true while the headline link is fitted on drifting-orbit years")
    method: str
    sources: list[str] = Field(description="VIIRS sensors used, in order of preference per day")
    values: list[list[float | None]] = Field(description="[year][period] harmonized estimate; null = no data")
    lo: list[list[float | None]] = Field(description="90% band, lower")
    hi: list[list[float | None]] = Field(description="90% band, upper")
    coverage: list[list[Literal["full", "partial", "none", "absent"]]]
    data_days: list[list[int]]
    estimated_days: list[list[int]] = Field(description="days whose value is a VIIRS-based estimate, not observed")
    substituted_days: list[list[int]] = Field(description="estimated days from a sensor other than the reference")
    band_note: str
    caveats: list[str]


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
    harmonized: HarmonizedOut | None = Field(description="null for the detections metric or before harmonization")
    harmonized_unavailable: str | None = None
    notes: list[str]


def sensor_note(name: str, chain) -> str | None:
    times = (chain.headline.report.get("overpass_local_solar_time", {}) if chain else {})
    if name == "Terra-MODIS":
        return f"Morning orbit (daytime passes near {times.get('Terra', '09:00-10:30')} local time): not comparable " \
               "with the afternoon headline series."
    if name == "Aqua-MODIS":
        when = f"; in this data its daytime passes are near {times['Aqua']} local time" if "Aqua" in times else ""
        return f"Drifting orbit from 2022 (designed for 13:30){when}. Before 2022 it is the headline reference."
    return None


def headline_caveats(chain) -> list[str]:
    r = chain.headline.report
    out = []
    if chain.headline.provisional:
        span = sorted({str(f)[:4] for f in r.get("folds", [])})
        years = (span[0] if len(span) == 1 else f"{span[0]}-{span[-1]}") if span else "the available data"
        out.append(f"Provisional: calibrated on {years}, when Aqua's orbit had already drifted. The calibration on "
                   "Aqua's stable years (2013-2021) replaces it when that data is ingested.")
    out.append("Estimate of what Aqua-MODIS would have counted at its original afternoon overpass, from VIIRS. "
               "Years when Aqua flew its original orbit show Aqua observed instead.")
    misses = [d["observed_over_predicted"] for d in r.get("residual_drift", []) if d["observed_over_predicted"]]
    if misses:
        out.append(f"Out-of-sample monthly error of the estimate: {min(misses) - 1:+.0%} to {max(misses) - 1:+.0%}.")
    if r.get("month_effects_validated") is False and chain.headline.method == "region_month_shrunk_ratio":
        out.append("One year of data can't validate seasonal ratios, so one ratio per region is used all year.")
    return out


class AOIListItem(BaseModel):
    name: str
    label: str
    bbox: list[float]


def contains(outer: tuple, inner: tuple) -> bool:
    w, s, e, n = outer
    iw, is_, ie, in_ = inner
    return w <= e and iw <= ie and w <= iw and ie <= e and s <= is_ and in_ <= n


def pick_store(store: CalendarStore, bbox: tuple) -> CalendarStore:
    """An ingested AOI's multi-year store when the request lies inside that AOI (ticket 07); else the global
    multi-year tiles for the box (2012-2026); else (no tiles, or a box too large for them) the global store."""
    for aoi_bbox, aoi_store in STORE.get("aoi", {}).values():
        if contains(aoi_bbox, bbox):
            return aoi_store
    tiles = STORE.get("tiles")
    return (tiles.store_for(bbox) if tiles is not None else None) or store


TOO_LARGE = ("This box is too large for the 15-year record (it would hold more than {rows:,} daily cell rows), so "
             "only the latest year is shown. Draw a smaller box (up to roughly 40° x 40° in fire-heavy regions).")


def too_large_message(bbox: tuple) -> str | None:
    tiles = STORE.get("tiles")
    if tiles is None or any(contains(b, bbox) for b, _ in STORE.get("aoi", {}).values()):
        return None
    return TOO_LARGE.format(rows=tiles.max_rows) if tiles.too_large(bbox) else None


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
    store = pick_store(store, area.bbox)
    cells, snapped = grid_cells(area.bbox, store.grid_deg)
    if cells == 0:
        raise HTTPException(422, f"the box contains no {store.grid_deg}° grid cell centre; draw a larger box")
    cal = store.calendar(area.bbox, metric, unit)
    clean = lambda v: None if math.isnan(v) else round(float(v), 3)
    grid = lambda a: [[clean(v) for v in row] for row in a]
    harmonized, why_not = None, None
    if metric != "cell_days":
        why_not = "harmonized values are fitted for fire cell-days only"
    elif (h := store.harmonized(area.bbox, unit)) is None:
        why_not = "no harmonization fitted yet - run `godseye harmonize`"
    else:
        chain = store.chain
        harmonized = HarmonizedOut(
            label=chain.label, target=chain.target, provisional=chain.headline.provisional,
            method=display_method(chain.headline), sources=chain.priority, values=grid(h.values), lo=grid(h.lo),
            hi=grid(h.hi), coverage=h.coverage.tolist(), data_days=h.data_days.tolist(),
            estimated_days=h.estimated_days.tolist(), substituted_days=h.substituted_days.tolist(),
            band_note=("90% range from out-of-sample tests, for weekly totals" if unit == "week" else
                       "no range in day view: the calibration is for weekly totals"),
            caveats=headline_caveats(chain))
    return CalendarResponse(
        aoi=AOIOut(name=area.name, label=area.label, bbox=list(area.bbox), grid_bbox=snapped, cells=cells),
        unit=unit, metric=metric, metric_label=METRIC_LABELS[metric], years=cal.years, periods=cal.periods,
        period_days=cal.period_days,
        data_range=[store.first.strftime("%Y-%m-%d"), store.last.strftime("%Y-%m-%d")],
        sensors=[SensorCalendar(sensor=name, note=sensor_note(name, store.chain), values=grid(cal.values[i]),
                                coverage=cal.coverage[i].tolist(), data_days=cal.data_days[i].tolist())
                 for i, name in enumerate(store.sensors)],
        harmonized=harmonized, harmonized_unavailable=why_not,
        notes=NOTES,
    )
