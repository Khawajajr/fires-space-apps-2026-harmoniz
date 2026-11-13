# Hackathon changelog

Times are Asia/Amman.

## 2026-11-13 (pre-event prep)
- Inventoried the FIRMS data: 51,019,714 rows, global, 2026-01-01 → 2026-11-06 only. No multi-year archives on disk yet.
- `git init`; tagged the pre-event prototype as `v0-prototype`.
- gods-eye-view: our changes committed on branch `space-apps-2026` (4 commits on upstream c56d5f2).
- Added CLAUDE.md.
- Next: Matt Pocock skills setup, `/grill-with-docs` → GLOSSARY + ADRs 001–005 → tickets. Submit the FIRMS archive requests.
- Skills set up (local markdown tracker, single-context docs). `/grill-with-docs` rounds 1–2: GLOSSARY.md + ADRs 0001–0006
  (Aqua-equivalent headline, feather, web app primary, NOAA-20 risk label, validation blocks, activity gate).
- /to-spec + /to-tickets: spec and 14 tickets in .scratch/space-apps-2026/ (build order + cut order agreed). ADR 0006 gained the 5-year history minimum. Phase 0 done; starting ticket 01.
- Ticket 01 done: `godseye` package (config, CLI, clean/, risk/, api/), thin wrappers, FIRMS fixture, 40 tests, ruff clean.
  Contract test: the 4 endpoints are byte-for-byte identical to v0-prototype; retrain reproduces v1 exactly. Next: 03.
- Archive requests cover 2018→now: calibration window 2018–2021 (auto-extends to 2013–2021), simulated-switchover figure; ADR 0001, spec, glossary, tickets 07/08 updated.
- Ticket 03 done: per-sensor fire cells (0.01°), 0.25° sensor grid, sensor availability with coverage gaps, manifest, coverage chart.
  Found 14 S-NPP outage days in 2026 that would otherwise read as zero fire. Added docs/REFERENCES.md. Next: 04 (calendar tracer bullet).
- Ticket 04 done: `/api/calendar` + `/api/aois` (pydantic, seam-3 tests), `web/` calendar app at /app/ (offline, vendored
  Leaflet 1.9.4, Natural Earth basemap). Server ready in 1.5 s (was 9.2 s). Next: 05 (VIIRS continuity link).

## 2026-11-14 (before the 09:00 start)
- Ticket 04 committed (6a91c9c). Ticket 05 done: VIIRS continuity link, cross-validated. NOAA-20 ~ S-NPP within 1% (no correction),
  NOAA-21 x 1.027; bands cover 90.4–90.7% out of fold. Cross-sensor check finds S-NPP partial-delivery days. ADR 0007.
- Ticket 05 committed (9e94920) after review fixes (honest baseline statement, zero-aware band, whole-fold bootstrap, cross-check sensitivity -1.4%). docs/HANDOFF.md written. Next: 06.
- Ticket 06 done: provisional Aqua-equivalent in the calendar (region-ratio link S-NPP->Aqua, -10.6% vs global ratio),
  Aqua overpass measured at 15:24 local (drift), chain via VIIRS continuity links, held-out headline figure
  (Levant 1.03, Argentina 0.96 estimate/observed). Next: 09.
- Ticket 06 committed (3bb9808) after review fixes (ADR 0001 era switch, no day-view band, honest method/caveats). Handoff updated.
