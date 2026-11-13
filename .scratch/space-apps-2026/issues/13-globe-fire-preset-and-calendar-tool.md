# 13: Globe: fire preset + get_burning_calendar tool

**What to build:** In the gods-eye-view fork (branch `space-apps-2026`), a fire-only startup preset and a `get_burning_calendar` agent tool that answers "Is this week unusual for northern Jordan?" from our API. Cut candidate #1.

**Blocked by:** 10, 12

**Status:** done (preset is a link, not a code preset; see notes)

- [ ] The preset turns off CCTV, aircraft, ships and traffic, and keeps Active Fires + Wildfire Risk
- [x] `get_burning_calendar` beside `get_fire_risk`, with `node:test` tests
- [x] Upstream credit visible in the UI and README; upstream licence text untouched
- [x] No new failures in `npm test` beyond the known Windows one

## Comments

- Fork commit `09b62da` on `space-apps-2026`:
  - the `/api/gods-eye/calendar-now` proxy route (validated bbox, harmonized series only);
  - `getCalendarNow` on the source;
  - the `get_burning_calendar` tool, registered in boundaries and in `docs/TOOLS.md`;
  - 4 new tests.
- **Preset = share link** `#v=2&lat=32&lon=36&l=w` (Active Fires only). Giving Wildfire Risk a share-link token means editing upstream's pinned token-ledger tests, so we don't; the layer is one toggle away. Documented in `integrations/gods-eye-view/README.md`.
- **Tests:** upstream's runner hits ENAMETOOLONG on Windows (one call with 935 files). Run in batches of 300, the only failures are the known Windows one and a timing-sensitive KML test that passes alone (42/42).
