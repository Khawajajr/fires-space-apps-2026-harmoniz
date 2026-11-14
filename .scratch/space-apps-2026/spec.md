# Spec: F.I.R.E.S. harmonized burning activity calendar

**Status:** ready-for-agent

## Problem Statement

Fire managers, scientists and land managers want to know whether burning in an area they care about is normal for the time of year, when its critical periods are, and whether this week is unusual. NASA's active-fire record answers that only if MODIS (1 km, since 2000) and VIIRS (375 m, since 2012) are combined. But VIIRS sees many more, smaller detections, so naively combined series show an artificial jump in 2012, and every later satellite raises counts again. Today our prototype has one year of data, shares a schema across sensors without correcting for sensitivity, and its risk model mostly learns persistence, with metrics that are slightly optimistic.

## Solution

A web app where the user picks an AOI (named, or a drawn bounding box) and sees a multi-year burning activity calendar on one consistent scale: **Aqua-equivalent fire cell-days** (ADR 0001). Every sensor's observed series stays visible next to it. Harmonized values carry a 90% uncertainty band, coverage gaps are shown as "no data", and provisional calibrations are labelled. On top of the calendar the app shows climatology, anomalies, critical periods, "this week vs history", and a 7-day risk outlook whose skill is reported against baselines on an untouched test block. A secondary 3D globe (the gods-eye-view fork) offers the same answers through its AI assistant.

## User Stories

1. As a fire manager, I want to select a named AOI (Jordan, Levant, Argentina), so that I can review its burning history without drawing anything.
2. As a land manager, I want to draw a bounding box, so that I can review an area that isn't predefined.
3. As a fire manager, I want a year × week calendar of Aqua-equivalent fire cell-days, so that I can compare seasons across many years on one scale.
4. As a scientist, I want to toggle between raw per-sensor and harmonized views, so that I can see what harmonization changed.
5. As a scientist, I want each sensor's observed series (Terra, Aqua, S-NPP, NOAA-20, NOAA-21) kept separate, so that no counts are silently added across sensors.
6. As a scientist, I want every harmonized value to carry a 90% uncertainty band, so that I know how far to trust it.
7. As a scientist, I want provisional calibrations clearly labelled, so that I don't mistake a drifted-orbit fit for the final method.
8. As a fire manager, I want coverage gaps (before launch, outages, after S-NPP ended) shown as "no data", so that I never read missing data as zero fire.
9. As a scientist, I want Terra-only months (Nov 2000 – Jun 2002) flagged "not comparable (morning orbit)", so that I don't compare them with afternoon-overpass years.
10. As a scientist, I want Aqua from 2022 labelled "drifting orbit" and the headline taken from VIIRS mapped to Aqua-equivalent, so that the record keeps one overpass time.
11. As a scientist, I want S-NPP mapped to Aqua-equivalent plotted from 2012 alongside Aqua observed, so that I can judge agreement in the overlap.
12. As a scientist, I want a figure showing a raw MODIS→VIIRS switchover with its artificial jump next to the harmonized series, so that the correction is visible at a glance. Until pre-2018 data exists this is a clearly labelled simulated switchover (MODIS-only 2018–2021, then VIIRS-only 2022–2025); the real 2012 transition replaces it if the early years arrive.
13. As a scientist, I want the calibration method chosen by out-of-sample error among a global ratio, a region × month ratio with shrinkage, and quantile mapping, so that the choice is justified, not assumed.
14. As a scientist, I want a drift check on 2022–2026, so that I know whether the calibration-window coefficients still hold.
15. As a scientist, I want the VIIRS-to-VIIRS continuity link (S-NPP ↔ NOAA-20 ↔ NOAA-21) validated separately, so that post-S-NPP years stay on the same scale.
16. As a fire manager, I want a seasonal profile (weekly median with p10–p90), so that I can see the typical shape of the year.
17. As a fire manager, I want the critical periods ranked, so that I can plan resources around the AOI's fire seasons.
18. As a fire manager, I want an anomaly list (weeks ≥ p90 or z ≥ 2, inside the activity gate), so that I can find unusual weeks without off-season noise.
19. As a fire manager in a sparse-fire AOI, I want an explicit "too little detected activity to define critical periods" message, so that the app doesn't invent a season out of noise.
20. As a fire manager, I want a "this week vs history" card with a percentile and plain-language status, so that I can brief others quickly.
21. As a fire manager, I want a 7-day risk outlook per 0.25° cell, so that I can anticipate where activity is likely next week.
22. As a scientist, I want risk skill reported on an untouched test block against persistence and a "2026 frequency to date" baseline, so that the numbers are honest.
23. As a scientist, I want skill reported separately on the new-activity subset, so that I know whether the model adds value beyond persistence.
24. As a scientist, I want a reliability diagram and calibrated probabilities, so that a forecast "30%" means about 30%.
25. As a scientist, I want per-region and spatial-block results, so that I know the model isn't memorizing places.
26. As a scientist, I want per-prediction feature contributions, so that I can see why a cell was rated high.
27. As a scientist, I want the risk label based on NOAA-20 alone, so that the base rate doesn't drift with the constellation (ADR 0004).
28. As a judge, I want every reported number reproducible by one command, so that I can trust the results.
29. As a judge, I want a model card and data card stating intended use, limitations and failure modes, so that I can assess validity.
30. As a demo presenter, I want the web app to work offline and to show its first calendar within 10 s of a cold start, so that the live demo is reliable.
31. As a globe user, I want to ask the assistant "Is this week unusual for northern Jordan?", so that I get the calendar answer conversationally.
32. As a globe user, I want a fire-only startup preset, so that unrelated layers don't distract.
33. As a contributor, I want `python -m godseye <command>` to run every pipeline step, so that the project is reproducible from a fresh clone.
34. As a contributor, I want the four existing endpoints to keep returning the same JSON, so that the globe integration keeps working during the refactor.
35. As a reviewer, I want data sources, libraries, upstream code and AI tools credited, so that attribution is complete.
36. As an operator, I want the ingest report to state, per AOI, how many weeks per year pass each activity gate and which rule was applied, so that the ADR 0006 rule is auditable.

## Implementation Decisions

- **Package `godseye`** with modules: config, ingest, clean, harmonize, calendar, risk, api, plus an argparse CLI. The old scripts become thin wrappers. The display name "F.I.R.E.S." is one config value.
- **Config:** YAML for pipeline settings and named AOIs (bbox + label), with env overrides for the data dir and the FIRMS key. One source of truth for grid, horizon, bins and paths.
- **Storage:** feather/zstd only, and numpy-only statistics (ADR 0002). Data and model binaries are never in git. A manifest records file, source, date range, rows and sha256.
- **Aggregates:** per sensor, per day, on two grids: 0.01° (fire cell-days) and 0.25° (risk and globe). Satellites are never summed. A per-sensor availability table defines coverage gaps (ADR / glossary: coverage gap).
- **Harmonization (ADR 0001):** the headline is Aqua-equivalent fire cell-days. Links: NOAA-20/21 → S-NPP (fit on their whole multi-year overlaps, 2018–2026 and 2023–2026). S-NPP → Aqua-equivalent (fit on the 2013–2021 calibration window, leave-one-year-out over 9 years; a provisional 2026 fit only when no archive is ingested). Three candidate methods, chosen by leave-one-out CV (by year when multi-year, by month on 2026), with the band from bootstrapping. Output: a coefficients table + a report (method, CV scores, caveats, provisional flag).
- **Calendar:** ISO-week primary, day drill-down. Pre-aggregated per AOI, never scanning raw rows per request. Climatology per week of year (median, p10, p90, probability of any activity). Activity gate per ADR 0006 (10% → relative top-20% if < 8 weeks/yr pass → floor at < 1 Aqua-equivalent cell-day/week). Anomalies ≥ p90 or z ≥ 2 inside the gate. Critical periods are contiguous weeks above the gate, ranked.
- **API contracts** (pydantic models, bbox or named AOI): `calendar` (unit day|week, metric cell_days|detections → per-sensor raw, harmonized + band, coverage flag, provisional flag), `calendar/climatology`, `calendar/anomalies`, `calendar/critical-periods`, `calendar/now`, plus `meta` (coverage, sensors, model version, attribution). The four existing endpoints keep their JSON.
- **Risk v2 (ADRs 0004, 0005):** label = ≥1 NOAA-20 fire cell-day in the 0.25° cell in t+1..t+7. VIIRS features come from NOAA-20 only. The MODIS-only brightness feature is dropped. Blocks: train ≤ 08-21, validation 08-28..09-25, test 10-02..10-30 (scored once). Trained from scratch with the native LightGBM API. Artifact = native model text + metadata JSON (features, params, data window, data hash, metrics, git SHA). A one-time loader reads the old pickle. Evaluation: ROC-AUC, PR-AUC, Brier, BSS vs persistence and vs "2026 frequency to date" (true NOAA-20 climatology only for AOIs with 2020–2025 archives), reliability + numpy Platt/isotonic, new-activity subset, per-region, 5° spatial blocks, data-justified thresholds, gain + `pred_contrib`.
- **Web (ADR 0003):** our own primary app with vendored JS: map + AOI select/draw → calendar heatmap (raw/harmonized toggle) → seasonal profile → anomalies → critical periods → this week vs history → next 7 days. Limitations, coverage notes and credits are always visible.
- **Globe fork:** on the `space-apps-2026` branch. Adds a `get_burning_calendar` tool beside `get_fire_risk`, plus a fire-only startup preset. Upstream credit stays visible; upstream licence text is unchanged.

## Testing Decisions

- Good tests check external behaviour at a seam (inputs → outputs), never internals. Use a tiny committed FIRMS fixture (a few hundred rows per sensor) covering: zero-padded `acq_time`, VIIRS `l/n/h` confidence, MODIS 0–100 confidence, type 1/2 rows, the SNPP `instrument` value "SNPP", VIIRS NRT without a `type` column, NRT `version` strings, and an antimeridian bbox.
- **Seams (fixed, no more during the hackathon):**
  1. `clean.harmonize_schema`: raw FIRMS rows → unified rows.
  2. `harmonize`: per-sensor series + coefficients → harmonized series + band (plus fitting on synthetic series with a known ratio).
  3. The `calendar` API contract (including the coverage flag, provisional flag and the ADR 0006 gate outcomes on synthetic AOIs).
  4. `risk.evaluate`: predictions + labels → metrics (checked against hand-computed values; leakage guards on block boundaries).
- Contract test: the four existing endpoints return the same JSON before and after the refactor.
- Prior art: the prototype has no Python tests. The globe fork's `node:test` files (provider, risk raster, fireRisk tool) are the model for the JS side.
- CI: ruff + pytest on the fixture.

## Out of Scope

- Pixel-level cloud masks (MOD14/VNP14 granules). Cloud cover is a documented limitation.
- Harmonizing FRP. It stays per sensor.
- Ignition-level or point-scale fire prediction. The risk outlook is a planning aid at 0.25°.
- Warm-starting v2 from v1. Daily NRT warm-start updates only if time remains after the quality gate.
- Parquet, scipy, sklearn, geopandas/shapely at runtime.
- Editing upstream gods-eye-view tests, including the known Windows failure.

## Further Notes

- Data: 2012–2025 global FIRMS archive (39 yearly zips, read in place) + 2026 global files in `data/raw` (51,019,714 rows, 2026-01-01 → 11-06; S-NPP ends 11-02). The calendar spans 2012–2026 (15 years), so the ADR 0006 ≥5-year rule passes. No Terra-only years (2000–2002) and no MODIS-only era: the headline figure's MODIS → VIIRS switch is simulated inside the overlap (updated 2026-11-14).
- Team Space Jo, NASA Space Apps Amman. Deadline Sun 15 Nov 23:59 (Amman); submission kit by 20:00.
- Glossary: `GLOSSARY.md`. ADRs: `docs/adr/0001`–`0006`.

## Build order and cut order (agreed 2026-11-13)

- **Build:** 01 → 03 → 04 → 05 → 06 → 09 → 10, then 11a → 12, then 07/08 whenever the archives land, then 11b, then 13. 02 runs alongside, before 11a.
- **Cut if time runs short, in this order:** 13 → per-cell contributions in 12 → spatial blocks in 11b → 10.
- **Never cut:** 05, 06, 09.
