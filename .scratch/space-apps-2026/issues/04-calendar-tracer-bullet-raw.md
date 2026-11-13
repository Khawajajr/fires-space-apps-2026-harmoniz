# 04: Calendar tracer bullet: raw per sensor

**What to build:** A user opens `web/`, picks a named AOI or draws a bbox, and sees a year × week heatmap of observed fire cell-days per sensor. Coverage gaps show as "no data". This is the first demoable product and our safety net.

**Blocked by:** 03

**Status:** ready-for-agent

- [ ] `GET /api/calendar?aoi=|bbox=&unit=day|week&metric=cell_days|detections`: per-sensor raw series + coverage flag (pydantic)
- [ ] Pre-aggregated; < 1 s for a country-size AOI
- [ ] `web/` with vendored JS (no CDN): map, AOI select + bbox draw, heatmap, sensor picker; limitations note and credits footer always visible
- [ ] Seam 3 contract tests (incl. coverage flag)
- [ ] Cold start to first calendar < 10 s
