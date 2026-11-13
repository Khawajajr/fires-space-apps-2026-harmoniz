# 03: Per-sensor daily aggregates + coverage table (2026)

**What to build:** From the 2026 FIRMS files (read in place), the pipeline writes per-sensor daily fire cell-days and detections on the 0.01° and 0.25° grids, a sensor availability table that defines coverage gaps, and a data manifest.

**Blocked by:** 01

**Status:** ready-for-agent

- [ ] Per sensor (Terra, Aqua, S-NPP, NOAA-20, NOAA-21) × day × cell, never summed across sensors
- [ ] Availability table: operational dates, outages, zero-record days, S-NPP end on 2026-11-02
- [ ] `data/manifest.json`: file, source, date range, rows, sha256
- [ ] Sensor × date coverage chart saved to `reports/figures/`
- [ ] Re-running is idempotent; tests on the fixture
