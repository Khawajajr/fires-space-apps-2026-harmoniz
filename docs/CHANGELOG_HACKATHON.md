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
- Ticket 09 built: climatology / ADR 0006 gate / anomalies (leave-one-year-out) / critical periods, API + UI panels.
  Real data shows 'needs ≥5 years (currently 1)'; checked populated on a synthetic 8-year store. ADR 0006 amended:
  'active' = ≥10% of the AOI's peak weekly median.
- Ticket 09 review fixes: ADR 0006 amendment moved back to PROPOSED (config switch, approved rule is default),
  anomaly/gate/floor fixes, helpers for 10. User asleep: FOR_ME_TObeDONE.md lists decisions and manual steps.
- Ticket 10 built: /api/calendar/now + 'This week vs history' card; incomplete current year now gets anomalies.
- Ticket 10 committed (6b6413b). Ticket 02 built: native LightGBM model + metadata (pickle migrated, identical
  predictions), GET /api/meta.
- Ticket 02 committed (c504eb8). Ticket 11a: risk v2 (NOAA-20 label, 3 blocks, no refit); validation ROC-AUC 0.905
  vs persistence 0.782; test block untouched until 11b.
- Ticket 11a committed (68e5bb9). Ticket 12: v2 served (config switch), schema contract test, 'Next 7 days' panel.
- Ticket 11b: test block scored once. Calibrated v2 ROC-AUC 0.867 vs persistence 0.749, Brier skill +0.197;
  new-activity BSS +0.089; MODEL_CARD.md generated. Ticket 12 review fixes.
- Ticket 13: get_burning_calendar globe tool + proxy route (fork 09b62da), fire-only share-link preset, integration README.
- Phase 7: README (hero figure, quickstart, results with baselines, limitations), ARCHITECTURE (mermaid), DATA_CARD, METHODOLOGY, AI_USAGE, LICENSE, CI (ruff + pytest + fresh-clone demo), secret scan clean; fresh clone -> demo verified.
- CI green on GitHub (lint, tests, fresh-clone demo). Phase 8: SUBMISSION.md (all fields, 30 s video + 7 slides),
  DEMO_SCRIPT.md (3 min), FOR_ME_TObeDONE.md updated. Waiting on archive files for 07/08.
- Ticket 07 code ready ahead of the data: godseye ingest --aoi, multi-year AOI stores, API routing; synthetic e2e tests.
- Ticket 08 code ready ahead of the data: archive pre-drift calibration (leave-one-year-out, not provisional), drift check from 2022, switchover figure; synthetic e2e tests. Archive day = 5 commands (FOR_ME_TObeDONE.md).
- 08:00-08:59: global FIRMS archive arrived (39 yearly zips 2012-2025, verified by the user). `godseye ingest-archive`:
  one parallel, resumable pass (14.4 min) -> AOI stores 2012-2026 (Levant with Jordan, Argentina), global 10-degree
  calibration table, availability 2012-2025, NOAA-20 2019-2025 weekly climatology; 558,898,261 rows in the manifest.
  ADR 0006 relative-activity amendment ACCEPTED before any multi-year data was merged. Calendar app now at `/`.
- Multi-year calibration (08): headline link on 2013-2021, 9 yearly folds, region x month ratios, WAPE 0.086 vs 0.242
  (global ratio), not provisional; VIIRS links on their multi-year overlaps; drift check: Aqua 0.97-1.04 to 2025,
  0.905 in 2026. Switchover headline figure. Calendar panels on for Levant, Jordan, Argentina (15 years).
- Risk v2.1 (+ NOAA-20 climatology feature) kept by the pre-declared validation rule (Brier 0.0906 vs 0.0929);
  test ROC-AUC 0.880 vs 0.867 (v2), BSS +0.194 vs climatology. Last commit before the start: aad486f (08:59:50),
  tagged `event-start`.

## 2026-11-14 (after the 09:00 start)
- Docs updated to the multi-year results: README hero figure and results, SUBMISSION (incl. what existed before the
  start), DEMO_SCRIPT, DATA_CARD, METHODOLOGY, ADR 0001, spec, tickets 07/08, HANDOFF, FOR_ME_TObeDONE.
- 09:50 /api/meta: data_range is now the range over all calendar stores (2012-01-01 -> 2026-11-06), plus a per-store list (global 2026; levant, argentina 2012-2026).
- 10:00 2026 Aqua NRT check: the 2026 drift-check shortfall is not an NRT artifact. Observed/predicted is 0.905 for Jan-Jul 2026 (both sensors archive quality), 0.916 for Aug (S-NPP NRT) and 0.892 for Sep-Oct (both NRT), vs 0.999 / 1.061 / 1.029 for the same months of 2025; the decline starts around Mar 2026 (gradual: orbit drift). The monthly series is now in the drift check (harmonization_report.json, monthly_after_window).
- 10:05 Critical periods: an area where every week passes the activity gate now says 'Active all year: no distinct critical period' (API all_year + summary; UI) instead of a 52-week period. Note text no longer calls the ADR 0006 amendment 'proposed'.
- 10:20 'This week' made current: public FIRMS global 7-day NRT files (MODIS, NOAA-20, NOAA-21; 857,672 rows, 7 Nov 00:00 -> 14 Nov ~04:16 UTC) added to data/raw/FIRMS_NRT_7d_20261114 and the manifest; clean (9 min) + aggregate + archive merge re-run. All sensors ok 7-13 Nov; 14 Nov partial (still being delivered); NOAA-20 6 Nov now flagged partial (the earlier download caught it half-delivered). 'This week' is week 46 (9-15 Nov, 6 days). Next 7 days now issued 13 Nov (last full NOAA-20 day), valid to 20 Nov. Links unchanged (S-NPP ended, no new pairs). data_age_days counts from the week's last day with data.
- 10:35 Contract test: the 2026 NRT update changed the 'recent fires' answers (they cover the newest 7 days), so the v0 golden fingerprints were re-captured by running the v0-prototype code itself (temporary worktree of tag v0-prototype, port 8011) on the same new data: our API matches v0 exactly on all fire endpoints. (Commit 5547ad7 was pushed before this re-capture; the contract test only runs locally with real data.)
