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
