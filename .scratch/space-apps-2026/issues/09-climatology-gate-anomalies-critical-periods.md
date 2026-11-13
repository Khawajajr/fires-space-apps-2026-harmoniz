# 09: Climatology, activity gate, anomalies, critical periods

**What to build:** For the selected AOI, the user sees a seasonal profile (weekly median, p10–p90), anomalies and ranked critical periods. All of them obey the ADR 0006 rules, which were fixed in advance. **Never cut.**

**Blocked by:** 06

**Status:** ready-for-agent

- [ ] `GET /api/calendar/climatology`, `/anomalies`, `/critical-periods` (pydantic)
- [ ] < 5 years of history → panels show "needs ≥5 years of history (currently N)"; the calendar is still shown
- [ ] Gate: ≥ 10% activity probability; relative top-20% if < 8 weeks/yr pass; floor at < 1 Aqua-equivalent cell-day/week → "too little detected activity to define critical periods"
- [ ] Anomalies ≥ p90 or z ≥ 2, only in gated weeks
- [ ] `web/` panels: seasonal profile, anomaly list, critical periods
- [ ] Tested on a synthetic multi-year fixture that covers every rule branch, so it's ready the moment 07 lands
