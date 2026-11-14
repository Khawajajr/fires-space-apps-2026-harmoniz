# Headline series is Aqua-equivalent fire cell-days (afternoon overpass)

The record spans sensors with different pixel sizes and overpass times, so we express the whole calendar on one scale: Aqua-MODIS at its nominal ~13:30 overpass, in fire cell-days (0.01° cells with ≥1 detection), which are far less sensitive to pixel size than detection counts. Terra is never mixed in, because its morning orbit sees a different part of the diurnal fire cycle.

- **Nov 2000 – Jun 2002:** Terra only, shown as its own series, flagged "not comparable (morning orbit)".
- **Jul 2002 – 2021:** Aqua observed is the headline. S-NPP mapped to Aqua-equivalent is plotted from 2012 as the agreement check.
- **2022 onward:** Aqua's orbit drifts, so the headline is VIIRS (S-NPP, then NOAA-20/21 after S-NPP ended on 2 Nov 2026) mapped to Aqua-equivalent with coefficients fitted on the **calibration window** (see "Data actually available" below). Aqua observed stays visible, labelled "drifting orbit". NOAA-20/21 are first mapped to S-NPP in their own overlap.

Detections are a secondary metric, shown raw per sensor (harmonized detections were dropped for the hackathon: the links are fitted and validated on fire cell-days only, and the API says so). FRP stays per sensor and is never harmonized. The method (global ratio vs region × month ratio with shrinkage vs quantile mapping) is chosen by out-of-sample error (leave one year out; one month out while there is a single year) under ADR 0007, and the 90% band comes from the chosen link's out-of-sample errors (the bootstrap over years gives the CI of the ratio).

## Considered options

- Combined Terra+Aqua MODIS as the reference: rejected because it mixes two overpass times and Terra's own drift.
- VIIRS-equivalent (back-cast MODIS upward): rejected because it invents detail MODIS never observed.

## Data actually available (updated 2026-11-14)

The FIRMS archive arrived as **global yearly files for 2012–2025** (MODIS from 2012, S-NPP from 2012-01-20, NOAA-20 from 2018-04-01, NOAA-21 from 2023-03-01), plus the 2026 files. So:

- **Calibration window = 2013–2021**, global: Aqua and S-NPP both delivering, before Aqua's drift. Validation is leave-one-year-out over 9 years, so month effects are validated (they ship), the 90% band comes from held-out years, and the bootstrap over years gives the CI of the ratio. The link is **not provisional**.
- **VIIRS continuity links** are fitted on their whole multi-year overlaps: NOAA-20 ↔ S-NPP 2018-04 → 2026, NOAA-21 ↔ S-NPP 2023-03 → 2026, leave-one-year-out.
- **Record shown:** 2012–2026 (15 years). There is no Terra-only segment (2000–2002) and no MODIS-only era, so the real MODIS → VIIRS transition can't be shown.
- **Headline figure:** a clearly labelled **simulated** switchover, placed inside the real overlap (MODIS raw to 2015, then the VIIRS satellites' raw counts added as each arrives). It shows the jumps at the switch and when NOAA-20 (2018) and NOAA-21 (2023) are added, next to the harmonized Aqua-equivalent series with its band and the 2013–2021 agreement check.

## Result (2026-11-14)

- **S-NPP → Aqua:** region × month ratios with shrinkage (k = 10). Region-month WAPE is 0.086, against 0.242 for one global ratio (−65%). The global ratio is 0.245 (90% CI 0.243–0.247), and band coverage on held-out years is 92.0%.
- **NOAA-20 → S-NPP:** no correction (ratio 0.994, CI 0.992–0.996; identity ties the global ratio within the 2% tolerance).
- **NOAA-21 → S-NPP:** one global ratio, ×1.027 (CI 1.026–1.029).
- **Drift check** (Aqua observed / predicted from S-NPP, global, per year): 0.97–1.04 for 2013–2021 (in the window), 1.00/1.02/1.04/1.01 for 2022–2025, and **0.905 in 2026**. The trend after the window is −0.021 per year, driven by 2026. So Aqua's drift barely moved fire cell-days until 2025, but by 2026 (overpass ~15:24) Aqua reads about 10% low. This supports switching the headline to VIIRS from 2022.
- **Superseded:** the 2026-only provisional fit (WAPE 0.203, ratio 0.216) and its "same fires, different camera" figure.
