# Space Apps 2026 submission drafts (F.I.R.E.S., Team Space Jo, Amman)

Challenge: **Harmonization of MODIS and VIIRS Hot Spots**. Copy each section into the matching field on the project page. Numbers come from `reports/` and are reproducible with `python -m godseye harmonize` / `evaluate`.

## High-level summary (≤150 words)

Fire managers need to know whether burning in their area is normal for the season. NASA's fire record spans two generations of satellites: MODIS and VIIRS see the same fires with different pixel sizes and overpass times, so raw counts jump about four-fold when VIIRS takes over, and again as satellites are added. F.I.R.E.S. puts a 15-year global record (2012–2026, five satellites) on one scale, Aqua-MODIS-equivalent fire cell-days, with links chosen by leave-one-year-out tests and 90% uncertainty bands. Pick any area to see its burning calendar, fire season, unusual weeks, this week against 14 past years, and a calibrated 7-day outlook. Missing data is never shown as zero fire: satellite outages are flagged, and we measured Aqua's orbit drift (9.5% low in 2026). Built for Jordan, the Levant and Argentina; works for any area.

## Project details

**What it does:**
- A web app (and an optional 3D globe) where you pick a named area or draw a box. You then see:
  - a year × week burning activity calendar on one consistent scale, with every raw sensor one click away;
  - the seasonal profile, critical periods and unusual weeks;
  - "this week vs history";
  - a 7-day fire-risk outlook per 0.25° cell.
- Every estimate carries its 90% range and every model number its baseline.

**How it works:**
1. NASA FIRMS detections (MODIS C6.1; VIIRS 375 m from S-NPP, NOAA-20, NOAA-21) are cleaned to quality-filtered vegetation fires.
2. They are counted as fire cell-days per sensor (0.01° cells with any detection), which removes most of the pixel-size effect.
3. A daily availability table marks outages and partial deliveries.
4. Sensor links are fitted on days both sensors delivered full data, leaving one year out: the VIIRS satellites on their whole overlap (2018–2026, 2023–2026), VIIRS → Aqua on Aqua's stable-orbit years 2013–2021. We compare no correction, a global ratio, regional × month ratios with shrinkage, and quantile mapping, choose the simplest method that held-out tests can't beat, and build bands from held-out errors.
5. The calendar shows Aqua observed while its orbit was stable and VIIRS-based estimates after.
6. A LightGBM model on NOAA-20 data (plus its 2019–2025 weekly climatology) gives the 7-day outlook, tested once on an untouched October block and calibrated.

**Benefits:**
- One honest, comparable record across satellite generations, for any area.
- Gaps and uncertainty are explicit.
- Answers for planners in plain language.

**Intended impact:** helps fire and land managers in Jordan, the Levant and beyond plan for their burning season, spot unusual activity early and brief others with numbers they can trust. It is open source and reproducible with one command per step.

**Tools and languages:** Python (pandas, NumPy, PyArrow, LightGBM, FastAPI, Pydantic, Matplotlib), JavaScript (Leaflet, plain JS; the globe fork uses Vite/CesiumJS), GitHub, Claude Code, Matt Pocock's agent skills.

## How NASA data was used

**NASA FIRMS** active fire detections, downloaded with the FIRMS archive tool, plus the FIRMS yearly MODIS summaries by country for 2000–2011. File list, dates, rows and sha256 are in `data/manifest.json`.
- **MODIS Collection 6.1** (MCD14ML) from Terra and Aqua.
- **VIIRS 375 m Collection 2:** S-NPP (VNP14IMG), NOAA-20 (VJ114IMG), NOAA-21 (VJ214IMG).
- **Coverage:** 2000-11-01 to 2026-11-14, global: 12 MODIS yearly files by country for 2000–2011 (49.6 million records, land only; Terra from 2000-11-01, Aqua from 2002-07-04), 39 yearly archive files for 2012–2025 (558.9 million records; S-NPP from 2012-01-20, NOAA-20 from 2018-04-01, NOAA-21 from 2023-03-01) plus 2026 archive and near-real-time files (51.0 million records). The archive files are read in place, never extracted.

FIRMS acknowledgement: "We acknowledge the use of data and/or imagery from NASA's Fire Information for Resource Management System (FIRMS), part of NASA's Earth Science Data and Information System (ESDIS)."

## Space Agency partner data

None used directly. The challenge was authored by CONAE (Argentina), and Argentina is one of our two focus areas.

## References

Copy from `docs/REFERENCES.md` (data, papers, code, libraries, AI tools). It includes gods-eye-view by Bilawal Sidhu (MIT), Natural Earth, Leaflet, Claude (Anthropic) and Matt Pocock's agent skills.

## Demo (choose one; limits are strict)

### Option A: ≤30-second video (shot list and captions)

| Time | Shot | Caption |
|---|---|---|
| 0–5 s | Headline figure (`headline_switchover.png`): the red naive record jumping | "NASA fire data since 2000. Every jump is a satellite change, not the fire." |
| 5–11 s | Same figure: the flat green harmonized line with its band | "We put five satellites on one scale, tested year by year on data the model never saw." |
| 11–18 s | App: pick Levant, the calendar fills; hover a week with its 90% range | "Pick any area: its burning calendar, with uncertainty." |
| 18–24 s | Hover an outage week (hatched / partial bar) | "Missing data is never zero fire: we flag satellite outages." |
| 24–30 s | Next 7 days panel: levels, metric vs persistence | "And a calibrated 7-day outlook. F.I.R.E.S., Team Space Jo, Amman." |

### Option B: ≤7 slides

1. **Title:** F.I.R.E.S.: one burning calendar across generations of NASA fire satellites (Team Space Jo, Amman).
2. **Problem:** the headline figure's red line. The jumps are the satellites, not the fires.
3. **Method:** fire cell-days, the sensor links, the simplest method that leave-one-year-out tests can't beat, bands from held-out errors.
4. **Proof:** the slide table below: WAPE 0.086 vs 0.242 for one global ratio, band coverage 90.7–92.0%, Aqua's drift caught in 2026.
5. **Product:** `reports/figures/app_calendar_levant.png` (and Jordan, Argentina): 2000–2026 calendar, season, unusual weeks, this week vs history, Next 7 days.
6. **Honesty:** outages flagged, metrics next to baselines (test ROC-AUC 0.880 vs 0.749 persistence and 0.816 climatology), limitations.
7. **Impact and next steps:** fire managers in Jordan and the Levant; more areas; the open-source repo link.

### Slide table (numbers from `reports/harmonization_report.json` and `reports/risk_evaluation.json`)

| | |
|---|---|
| Record | 2000–2026, global; 5 sensors (Terra, Aqua, S-NPP, NOAA-20, NOAA-21); Aqua-equivalent headline 2003–2026 |
| Real MODIS → VIIRS switch (2012) | naive record jumps 6.0× (Levant), 2.6× (Argentina); Aqua itself 0.95× / 0.81× |
| Terra → Aqua link (2003–2021, 19 folds) | WAPE 0.136 > 0.086: fails the rule fixed in advance, so Terra stays per sensor |
| Calibration window | 2013–2021 (Aqua's stable orbit), leave-one-year-out, 9 folds |
| NOAA-20 → S-NPP (2018–2026) | no correction; ratio 0.994 (90% CI 0.992–0.996); band coverage 91.1% |
| NOAA-21 → S-NPP (2023–2026) | one global ratio, ×1.027 (1.026–1.029); band coverage 90.7% |
| S-NPP → Aqua-equivalent (2013–2021) | region × month ratios (shrunk); global ratio 0.245 (0.243–0.247); WAPE 0.086 vs 0.242 for one global ratio; band coverage 92.0% |
| Aqua drift check | observed / predicted 0.97–1.04 in 2013–2025, 0.905 in 2026 (trend −0.021/yr after 2021) |
| Calendars | 5 named areas and any drawn box: 2000–2026, 24 history years (2003–2026; climatology, anomalies, critical periods, this week vs history all on) |
| Critical periods (ADR 0006) | Levant 5 May – 2 Mar (43 weeks, peak week 25); Jordan, Argentina, Paraná Delta active all year; N. Jordan forest belt too little activity (0.18 cell-days/week) |
| Risk v2, test 2–30 Oct 2026 | ROC-AUC 0.867, PR-AUC 0.731, Brier 0.106; BSS +0.197 vs persistence, +0.162 vs climatology |
| Risk v2.1 (served), same test | ROC-AUC 0.880, PR-AUC 0.749, Brier 0.102; BSS +0.228 vs persistence, +0.194 vs climatology |
| Baselines, same test | persistence 0.749 / 0.456 / 0.133; NOAA-20 2019–2025 climatology 0.816 / 0.605 / 0.127 |
| New activity (no fire in 30 days) | v2.1 ROC-AUC 0.749 (v2 0.694); BSS +0.121 vs persistence, +0.143 vs climatology |

## What existed before the start (Sat 14 Nov 09:00 Amman) and what was built after

Stated plainly, from `docs/CHANGELOG_HACKATHON.md` and the git history (times Asia/Amman):

- **Before the team's preparation (tag `v0-prototype`):** a working prototype by the team: a Leaflet dashboard, a FIRMS cleaning script, a LightGBM 7-day risk model (v1) and four API endpoints, plus our changes on a fork of gods-eye-view (MIT).
- **Pre-event preparation, Fri 13 Nov 22:19 to Sat 14 Nov 08:59** (commits `a03a3a1` to `aad486f`, tag `event-start`): most of the project as submitted.
  - Design (glossary, ADRs 0001–0007, spec and tickets).
  - The `godseye` package, per-sensor fire cells and availability.
  - The calendar app and API, the sensor links and their validation, climatology and anomalies.
  - Risk v2/v2.1 and the model card, the globe tool, CI and the docs.
  - On Sat morning (08:00–08:59): the ingest of the 2012–2025 archive, the multi-year calibration and the v2.1 decision.
- **After 09:00** (details in the "after the 09:00 start" section of the changelog):
  - per-store data ranges;
  - the Aqua NRT check;
  - data current to 14 Nov;
  - global 0.25° tiles for any drawn box;
  - the risk cache;
  - two focused areas (ADR 0008);
  - the Arabic UI;
  - the record extended back to 2000 with the real 2012 switch;
  - the static snapshot (`site/`).

## Final checklist (do these on the project page)
- [ ] All 5 team members registered and on the Members tab (Ahmad Khawaja, Alina Abandah, Omar Sawalmeh, Zaid Ghaith, Joud Musa).
- [ ] Challenge selected: **Harmonization of MODIS and VIIRS Hot Spots**.
- [ ] Public repository link (make `Khawajajr/fires-space-apps-2026` public first; see FOR_ME_TObeDONE.md).
- [ ] Public demo link (the video, or the slides as a public link).
- [ ] Everything in English.
- [ ] References complete (from `docs/REFERENCES.md`).
- [ ] Submitted before **Sun 15 Nov 23:59 Amman** (aim for 20:00).
