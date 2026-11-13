# 04: Calendar tracer bullet: raw per sensor

**What to build:** A user opens `web/`, picks a named AOI or draws a bbox, and sees a year × week heatmap of observed fire cell-days per sensor. Coverage gaps show as "no data". This is the first demoable product and our safety net.

**Blocked by:** 03

**Status:** done

- [x] `GET /api/calendar?aoi=|bbox=&unit=day|week&metric=cell_days|detections`: per-sensor raw series + coverage flag (pydantic)
- [x] Pre-aggregated; < 1 s for a country-size AOI
- [x] `web/` with vendored JS (no CDN): map, AOI select + bbox draw, heatmap, sensor picker; limitations note and credits footer always visible
- [x] Seam 3 contract tests (incl. coverage flag)
- [x] Cold start to first calendar < 10 s

## Comments

- Measured on 2026 data: `/api/calendar` 27–105 ms (named AOIs, whole world, antimeridian box); server ready 1.5 s
  (risk scoring moved to a background thread, and the v0 timestamp formatting made ~6x faster with identical output);
  first calendar in the browser 120–200 ms after page load. No console errors (headless Chrome, light, dark, 390 px).
- The page is served at `/app/` for now. The v0 dashboard keeps `/` until the quality gate.
- Colour: one orange ramp, quantile bins of the values on screen, validated with the dataviz checker in both themes.
  Zero (observed, no fire), no data (hatched) and partial coverage (dot) are each visibly different.
- Review fixes:
  - Partial days keep their count but are always flagged. The glossary now says so; a bar along the top marks partial periods at any cell width.
  - New response fields: `data_days` per period and `period_days`; `absent` for ISO week 53 / day 366 that a year lacks (not a gap).
  - 422 for a box with no grid cell centre (it used to return zeros) and for west > east unless it crosses the antimeridian (west > 0 > east).
  - A one-sided antimeridian box no longer crashes.
  - Risk scoring failure: logged, 503, retried.
  - One shared `in_bbox`.
- Notes for 06/09/10:
  - Harmonized values go in a separate top-level block (`harmonized: values, lo, hi, coverage, provisional`).
  - Climatology must use `data_days` to exclude or scale partial weeks.
  - The store is reached through `calendar_api.STORE` and filled in the app lifespan; turn it into a dependency if a CLI step needs it.
