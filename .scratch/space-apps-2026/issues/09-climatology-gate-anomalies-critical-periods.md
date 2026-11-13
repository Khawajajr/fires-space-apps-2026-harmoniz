# 09: Climatology, activity gate, anomalies, critical periods

**What to build:** For the selected AOI, the user sees a seasonal profile (weekly median, p10–p90), anomalies and ranked critical periods. All of them obey the ADR 0006 rules, which were fixed in advance. **Never cut.**

**Blocked by:** 06

**Status:** done

- [x] `GET /api/calendar/climatology`, `/anomalies`, `/critical-periods` (pydantic)
- [x] < 5 years of history → panels show "needs ≥5 years of history (currently N)"; the calendar is still shown
- [x] Gate: ≥ 10% activity probability; relative top-20% if < 8 weeks/yr pass; floor at < 1 Aqua-equivalent cell-day/week → "too little detected activity to define critical periods"
- [x] Anomalies ≥ p90 or z ≥ 2, only in gated weeks
- [x] `web/` panels: seasonal profile, anomaly list, critical periods
- [x] Tested on a synthetic multi-year fixture that covers every rule branch, so it's ready the moment 07 lands

## Comments

- `calendar/climatology.py` (pure) + `api/climatology.py` (3 endpoints, `series=harmonized|<sensor>`, default harmonized).
- Method choices:
  - **Usable weeks:** full weeks, or partial weeks with ≥ 5 data days (scaled to 7). Thinner weeks are left out, never read as zero.
  - **History year:** at least 75% of its weeks usable.
  - **Pooling:** each ISO week pools ±1 week, and week 53 is pooled into 52.
  - **Anomalies:** leave-one-year-out, ≥ p90 (and above the median) or z ≥ 2, only in gated weeks. On the floor rule they're judged against the whole record.
  - **Critical periods:** runs of gated weeks wrapping over New Year, ranked by summed median.
- **ADR 0006 amendment: PROPOSED, not active.** "Active" would mean ≥ 10% of the AOI's peak weekly median. It sits behind `climatology.activity` (default `absolute`, as approved). A test shows the approved rule gates every week on noisy data. The user decides (FOR_ME_TObeDONE.md #1).
- Review fixes:
  - **ADR process:** the amendment is reverted to proposed.
  - **Anomalies:** both branches require v ≥ the active threshold.
  - **Relative rule:** exactly the top 20% (ties broken by median).
  - **Floor:** computed over the whole record.
  - **Gate counts:** reported for 07.
  - **For 10:** public `week_reference` + `percentile_of`.
  - **Gate:** empty climatology weeks never pass.
  - **Profile line:** breaks at gaps; the overlay scales partial weeks like the climatology does.
  - **UI:** each panel shows its own error.
  - **Notes:** built from the constants.
- Real data (2026 only): every panel says "needs ≥5 years of history (currently 1)". The populated panels were checked on a synthetic 8-year store: season 5 May – 31 Aug, the planted anomaly found first.
- Tests: 8 pure tests (every gate branch, wrap-around, partial weeks, history rule) and 5 API contract tests on an 8-year synthetic store.
