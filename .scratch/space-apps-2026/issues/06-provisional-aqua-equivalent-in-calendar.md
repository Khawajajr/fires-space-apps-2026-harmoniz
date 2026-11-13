# 06: Provisional Aqua-equivalent in the calendar

**What to build:** The calendar shows Aqua-equivalent fire cell-days with a 90% band, a raw/harmonized toggle and a visible "provisional (drifted-orbit calibration)" badge. The values come from a VIIRS → Aqua link fitted on 2026. **Never cut.**

**Blocked by:** 04, 05

**Status:** done

- [x] VIIRS → Aqua-equivalent link fitted on 2026 with the same 3 candidates and CV as 05; the report flags `provisional: true`
- [x] `/api/calendar` returns the harmonized value + band + provisional flag; Aqua observed is labelled "drifting orbit"
- [x] `web/`: raw/harmonized toggle, band, provisional badge
- [x] **Fallback headline figure** ("same fires, different camera") for Levant and Argentina: 2026 weekly raw S-NPP vs raw Aqua (showing the ratio), next to harmonized vs Aqua (ratio ≈ 1), labelled provisional, saved to `reports/figures/`
- [x] Seam 2 and 3 tests updated

## Comments

- **Headline link S-NPP → Aqua-MODIS (provisional, 2026, leave-one-month-out):**
  - The region-ratio method wins. Region-month WAPE is 0.203 vs 0.227 for the global ratio (−10.6%), and the band covers 92.6% out of fold.
  - Aqua sees about 21.5% of the fire cells S-NPP sees (global ratio 0.216). By month it ranges 0.19–0.25.
  - **Aqua's drift is measured:** median local solar time of its daytime detections is 15:24, against 13:34 for S-NPP and 13:30 for NOAA-20. Terra is at 09:09.
- **One year can't validate month effects.** With leave-one-month-out the held-out month has no region×month ratio, so only region ratios (shrunk to the global ratio) ship, with a caveat. They return automatically with multi-year folds (08). Drift caveats now use held-out observed/predicted per month, not the raw ratio.
- **Calendar:**
  - The `harmonized` block holds values, lo, hi, coverage, data_days and substituted_days, plus provisional, method, sources and caveats.
  - Each day uses the first VIIRS sensor with full data (S-NPP, then NOAA-20, then NOAA-21), converted with the 05 links, then mapped to Aqua-equivalent with **per-cell** region ratios.
  - The band is the headline band, widened in log space by the continuity band × the share of substituted days.
  - The value is null for detections (the link is fitted for fire cell-days), with a reason.
  - Aqua and Terra raw series carry notes (drifting orbit; morning orbit).
- **UI:**
  - A view toggle: "Aqua-equivalent" (default) / "By sensor".
  - A provisional badge listing the caveats.
  - Tooltips show the 90% range and the substituted days; the table view includes ranges.
- **Fallback headline figure** `reports/figures/headline_same_fires_different_camera.png`, every estimate held out (link refitted without that month):
  - Levant: Aqua sees 15% of S-NPP; estimate/observed 1.03, 98% of weeks in range.
  - Argentina: 27%; 0.96; 93%.
- Server ready in ~2.3 s; `/api/calendar` < 100 ms with the harmonized block.
- Review fixes:
  - **Era switch (ADR 0001):** Aqua observed is the headline up to `observed_until` (2021-12-31) on days Aqua delivered; after that, the VIIRS estimate. Each period has `estimated_days`, and the band covers only the estimated part. 2026 data: every day is an estimate.
  - The day view has no band (calibration is for weekly totals) and the API says so.
  - The method is described as shipped ("region ratios … month effects not validated").
  - Zero estimates are labelled as estimates.
  - The Aqua and Terra notes use the measured overpass times, and the Aqua note says "from 2022".
  - Caveats come from structured flags and include the out-of-sample monthly error range (−14% to +21%).
  - The headline figure's bands are built without the plotted month.
  - The AOI band check is labelled in-sample.
  - Reference-first check, region-key guard, "13:60" fix, invalid sensor in the URL handled.
  - Glossary (band, Aqua-equivalent) and ADR 0001 (detections not harmonized; band source) updated.
- Left for 08: S-NPP mapped to Aqua-equivalent shown next to Aqua observed for 2012/2018–2021 as the agreement series (story 11).
