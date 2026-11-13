# 03: Per-sensor daily aggregates + coverage table (2026)

**What to build:** From the 2026 FIRMS files (read in place), the pipeline writes per-sensor daily fire cell-days and detections on the 0.01° and 0.25° grids, a sensor availability table that defines coverage gaps, and a data manifest.

**Blocked by:** 01

**Status:** done

- [x] Per sensor (Terra, Aqua, S-NPP, NOAA-20, NOAA-21) × day × cell, never summed across sensors
- [x] Availability table: operational dates, outages, zero-record days, S-NPP end on 2026-11-02
- [x] `data/manifest.json`: file, source, date range, rows, sha256
- [x] Sensor × date coverage chart saved to `reports/figures/`
- [x] Re-running is idempotent; tests on the fixture

## Comments

- Outputs: `sensor_fire_cells` (0.01°), `sensor_grid_daily` (0.25°, with distinct fire cells per coarse cell), `sensor_availability` (status + `is_coverage_gap`), `data/manifest.json`, `reports/figures/coverage_sensor_date.png`. Counts are of kept detections (glossary).
- 2026 finding: S-NPP had 14 full-day outages (Mar 10–12, Apr 28–30, Jun 1–2, Jul 11–16) plus the end after Nov 2. Before this table they would have read as zero fire.
- Review follow-ups for 07 are listed there. Typed `aggregate` config and a single VIIRS/MODIS rule stay on 02's list.
