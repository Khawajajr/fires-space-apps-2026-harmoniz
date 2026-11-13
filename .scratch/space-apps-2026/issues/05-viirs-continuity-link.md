# 05: VIIRS ↔ VIIRS continuity link (final)

**What to build:** NOAA-20 and NOAA-21 fire cell-days are mapped onto the S-NPP scale using the 2026 overlap, so the VIIRS series continues after S-NPP ended. This link is final, not provisional (ADR 0001). **Never cut.**

**Blocked by:** 03

**Status:** ready-for-agent

- [ ] Candidates: global ratio, region × month ratio with shrinkage to the global prior, quantile mapping per region × season
- [ ] Leave-one-month-out CV: MAE / MAPE / correlation of weekly and monthly series; the chosen method beats the global ratio, or the report says it doesn't
- [ ] 90% band from bootstrapping over weeks
- [ ] Seam 2 tests (synthetic series with known ratios)
- [ ] Coefficients table + report (method, CV scores, caveats, `provisional: false`)
