# Headline series is Aqua-equivalent fire cell-days (afternoon overpass)

The record spans sensors with different pixel sizes and overpass times, so we express the whole calendar on one scale: Aqua-MODIS at its nominal ~13:30 overpass, in fire cell-days (0.01° cells with ≥1 detection), which are far less sensitive to pixel size than detection counts. Terra is never mixed in, because its morning orbit sees a different part of the diurnal fire cycle.

- **Nov 2000 – Jun 2002:** Terra only, shown as its own series, flagged "not comparable (morning orbit)".
- **Jul 2002 – 2021:** Aqua observed is the headline. S-NPP mapped to Aqua-equivalent is plotted from 2012 as the agreement check.
- **2022 onward:** Aqua's orbit drifts, so the headline is VIIRS (S-NPP, then NOAA-20/21 after S-NPP ended on 2 Nov 2026) mapped to Aqua-equivalent with coefficients fitted on **2013–2021**. Aqua observed stays visible, labelled "drifting orbit". NOAA-20/21 are first mapped to S-NPP in their own overlap.

Detections are a secondary metric, shown raw per sensor and also harmonized. FRP stays per sensor and is never harmonized. The method (global ratio vs region × month ratio with shrinkage vs quantile mapping) is chosen by leave-one-year-out error, and the uncertainty band comes from bootstrapping over years.

## Considered options

- Combined Terra+Aqua MODIS as the reference: rejected because it mixes two overpass times and Terra's own drift.
- VIIRS-equivalent (back-cast MODIS upward): rejected because it invents detail MODIS never observed.

## Until the 2002–2025 archives are ingested

Only 2026 data is on disk, and 2026 is a drifting-orbit year for Aqua. So the links are split:

- **VIIRS ↔ VIIRS (S-NPP ↔ NOAA-20 ↔ NOAA-21):** fitted and validated on the 2026 overlap now. Same orbit and instrument family, no drift: **not provisional**.
- **VIIRS → Aqua-equivalent:** any 2026 fit is a drifted-orbit calibration, labelled **"provisional"** in the report and the UI. If the archives aren't ingested by **Sat 14 Nov 18:00 (Amman)**, we ship the provisional link, say so in the README and the slides, and present the 2013–2021 fit as designed but not yet run.
