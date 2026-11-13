# Space Apps 2026 submission drafts (F.I.R.E.S., Team Space Jo, Amman)

Challenge: **Harmonization of MODIS and VIIRS Hot Spots**. Copy each section into the matching field on the project page. Numbers come from `reports/` and are reproducible with `python -m godseye harmonize` / `evaluate`.

## High-level summary (≤150 words)

Fire managers need to know whether burning in their area is normal for the season. NASA's fire record spans two generations of satellites. MODIS (since 2000) and VIIRS (since 2012) see the same fires with different pixel sizes and overpass times, so raw counts jump four- to seven-fold when VIIRS arrives. F.I.R.E.S. harmonizes them onto one scale, Aqua-MODIS-equivalent fire cell-days, using sensor links chosen by out-of-sample tests, with 90% uncertainty bands. Pick any area to see its burning activity calendar, fire season, unusual weeks, this week against past years, and a calibrated 7-day outlook. Missing data is never shown as zero fire: we detected 14 outage days and 10 partial-delivery days of the S-NPP satellite in 2026, and Aqua's overpass drifting to 15:24. Built for Jordan and the Levant, and Argentina, and works for any area.

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
4. Sensor links are fitted on days both sensors delivered full data. We compare no correction, a global ratio, regional ratios with shrinkage, and quantile mapping, choose the simplest method that held-out tests can't beat, and build bands from held-out errors.
5. The calendar shows Aqua observed while its orbit was stable and VIIRS-based estimates after.
6. A LightGBM model on NOAA-20 data gives the 7-day outlook, tested once on an untouched October block and calibrated.

**Benefits:**
- One honest, comparable record across satellite generations, for any area.
- Gaps and uncertainty are explicit.
- Answers for planners in plain language.

**Intended impact:** helps fire and land managers in Jordan, the Levant and beyond plan for their burning season, spot unusual activity early and brief others with numbers they can trust. It is open source and reproducible with one command per step.

**Tools and languages:** Python (pandas, NumPy, PyArrow, LightGBM, FastAPI, Pydantic, Matplotlib), JavaScript (Leaflet, plain JS; the globe fork uses Vite/CesiumJS), GitHub, Claude Code, Matt Pocock's agent skills.

## How NASA data was used

**NASA FIRMS** active fire detections, downloaded with the FIRMS archive tool. File list, dates, rows and sha256 are in `data/manifest.json`.
- **MODIS Collection 6.1** (MCD14ML) from Terra and Aqua.
- **VIIRS 375 m Collection 2:** S-NPP (VNP14IMG), NOAA-20 (VJ114IMG), NOAA-21 (VJ214IMG).
- **Coverage:** 2026-01-01 to 2026-11-06, global (51 million records). Archive requests for 2018 onwards for the Levant and Argentina are being added for the stable-orbit calibration.

FIRMS acknowledgement: "We acknowledge the use of data and/or imagery from NASA's Fire Information for Resource Management System (FIRMS), part of NASA's Earth Science Data and Information System (ESDIS)."

## Space Agency partner data

None used directly. The challenge was authored by CONAE (Argentina), and Argentina is one of our two focus areas.

## References

Copy from `docs/REFERENCES.md` (data, papers, code, libraries, AI tools). It includes gods-eye-view by Bilawal Sidhu (MIT), Natural Earth, Leaflet, Claude (Anthropic) and Matt Pocock's agent skills.

## Demo (choose one; limits are strict)

### Option A: ≤30-second video (shot list and captions)

| Time | Shot | Caption |
|---|---|---|
| 0–5 s | The raw S-NPP and Aqua lines side by side (headline figure, left panel) | "Same fires, different camera: VIIRS sees 4 to 7× more than MODIS." |
| 5–11 s | The right panel: harmonized estimate on top of Aqua observed, band visible | "We put both on one scale, tested on data the model never saw." |
| 11–18 s | App: pick Levant, the calendar fills; hover a week with its 90% range | "Pick any area: its burning calendar, with uncertainty." |
| 18–24 s | Hover an outage week (hatched / partial bar) | "Missing data is never zero fire: we flag satellite outages." |
| 24–30 s | Next 7 days panel: levels, metric vs persistence | "And a calibrated 7-day outlook. F.I.R.E.S., Team Space Jo, Amman." |

### Option B: ≤7 slides

1. **Title:** F.I.R.E.S.: one burning calendar across generations of NASA fire satellites (Team Space Jo, Amman).
2. **Problem:** the headline figure, left panel. The jump is the sensor, not the fire.
3. **Method:** fire cell-days, the sensor links, the simplest method that held-out tests can't beat, bands from held-out errors.
4. **Proof:** held-out agreement (Levant 1.03×, Argentina 0.96×), band coverage of about 90%, Aqua's drift measured at 15:24.
5. **Product:** screenshots of the calendar, the season panels and the Next 7 days panel.
6. **Honesty:** outages flagged, metrics next to baselines (test ROC-AUC 0.867 vs 0.749 persistence), limitations.
7. **Impact and next steps:** fire managers in Jordan and the Levant; the 2018–2021 calibration; the open-source repo link.

## Final checklist (do these on the project page)

- [ ] All 5 team members registered and on the Members tab (Ahmad Khawaja, Alina Abandah, Omar Sawalmeh, Zaid Ghaith, Joud Musa).
- [ ] Challenge selected: **Harmonization of MODIS and VIIRS Hot Spots**.
- [ ] Public repository link (make `Khawajajr/fires-space-apps-2026` public first; see FOR_ME_TObeDONE.md).
- [ ] Public demo link (the video, or the slides as a public link).
- [ ] Everything in English.
- [ ] References complete (from `docs/REFERENCES.md`).
- [ ] Submitted before **Sun 15 Nov 23:59 Amman** (aim for 20:00).
