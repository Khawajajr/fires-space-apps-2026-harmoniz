# 05: VIIRS ↔ VIIRS continuity link (final)

**What to build:** NOAA-20 and NOAA-21 fire cell-days are mapped onto the S-NPP scale using the 2026 overlap, so the VIIRS series continues after S-NPP ended. This link is final, not provisional (ADR 0001). **Never cut.**

**Blocked by:** 03

**Status:** done

- [x] Candidates: global ratio, region × month ratio with shrinkage to the global prior, quantile mapping per region × season
- [x] Leave-one-month-out CV: MAE / MAPE / correlation of weekly and monthly series; the chosen method beats the global ratio, or the report says it doesn't
- [x] 90% band from bootstrapping over weeks
- [x] Seam 2 tests (synthetic series with known ratios)
- [x] Coefficients table + report (method, CV scores, caveats, `provisional: false`)

## Comments

- Results (2026, fire cell-days on days both sensors delivered full data, leave-one-month-out):
  - **NOAA-20 → S-NPP: no correction.** Ratio 0.993, 90% CI 0.983–1.001 (whole-month bootstrap). Ties the global ratio within noise (WAPE 0.0317 vs 0.0322); band coverage 90.9%.
  - **NOAA-21 → S-NPP: global ratio 1.027**, CI 1.021–1.031; WAPE 0.0326 vs 0.0425 uncorrected; band coverage 90.5%.
  - The band transfers to AOI scale: whole-AOI weekly coverage is 91–98% for Jordan, Levant and Argentina.
  - The shrunk regional ratio (WAPE ≈ 0.034) and quantile mapping (≈ 0.155) lost: they fit noise.
- Added candidates and rules beyond the ticket:
  - "No correction" is a candidate.
  - Selection: the simplest method within 2% of the best (ADR 0007).
  - The band is the 90% predictive interval from held-out errors, binned by magnitude, and its out-of-fold coverage is reported. The bootstrap over weeks is reported as the ratio's CI.
- Finding that changed 03: S-NPP had partial-delivery days the global rule missed (down to 39% of NOAA-20 on Oct 13). A cross-sensor VIIRS check now marks them partial; MODIS is excluded.
- Caveat in the report: in October 2026, its last full month, S-NPP read about 2–4% low against both NOAA satellites, consistent with end-of-life decline. October stays in the calibration; leaving it out moves the ratios by ≤ 0.5% (0.993 → 0.998; 1.027 → 1.030).
- Review fixes:
  - An honest baseline statement (`versus_global_ratio`).
  - An additive band for observed zeros, and coverage now includes zero predictions.
  - Whole-fold bootstrap.
  - Weekly and monthly correlation, plus MAPE on region-months with y ≥ 50.
  - Sensitivity to the cross-sensor check: −1.4% without it; recorded as a caveat.
  - AOI-scale band check.
  - Links accept "YYYY-MM" months.
- Left for 06: chaining links (NOAA-21 → S-NPP → Aqua-eq) with a combined band. Applying a region-level winner to an AOI needs per-cell ratios before summing. A quantile-map winner can't be applied yet (it fails loudly).
- Left for 08: the notebook `02_harmonization_validation`.
- Outputs: `data/processed/harmonization_coefficients.feather`, `harmonization_report.json` (also in `reports/`), `reports/figures/harmonization_viirs_continuity.png`.
