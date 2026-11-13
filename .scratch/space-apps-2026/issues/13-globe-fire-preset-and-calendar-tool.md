# 13: Globe: fire preset + get_burning_calendar tool

**What to build:** In the gods-eye-view fork (branch `space-apps-2026`), a fire-only startup preset and a `get_burning_calendar` agent tool that answers "Is this week unusual for northern Jordan?" from our API. Cut candidate #1.

**Blocked by:** 10, 12

**Status:** ready-for-agent

- [ ] The preset turns off CCTV, aircraft, ships and traffic, and keeps Active Fires + Wildfire Risk
- [ ] `get_burning_calendar` beside `get_fire_risk`, with `node:test` tests
- [ ] Upstream credit visible in the UI and README; upstream licence text untouched
- [ ] No new failures in `npm test` beyond the known Windows one
