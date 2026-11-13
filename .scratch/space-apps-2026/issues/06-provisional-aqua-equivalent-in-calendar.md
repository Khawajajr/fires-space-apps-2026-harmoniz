# 06: Provisional Aqua-equivalent in the calendar

**What to build:** The calendar shows Aqua-equivalent fire cell-days with a 90% band, a raw/harmonized toggle and a visible "provisional (drifted-orbit calibration)" badge. The values come from a VIIRS → Aqua link fitted on 2026. **Never cut.**

**Blocked by:** 04, 05

**Status:** ready-for-agent

- [ ] VIIRS → Aqua-equivalent link fitted on 2026 with the same 3 candidates and CV as 05; the report flags `provisional: true`
- [ ] `/api/calendar` returns the harmonized value + band + provisional flag; Aqua observed is labelled "drifting orbit"
- [ ] `web/`: raw/harmonized toggle, band, provisional badge
- [ ] **Fallback headline figure** ("same fires, different camera") for Levant and Argentina: 2026 weekly raw S-NPP vs raw Aqua (showing the ratio), next to harmonized vs Aqua (ratio ≈ 1), labelled provisional, saved to `reports/figures/`
- [ ] Seam 2 and 3 tests updated
