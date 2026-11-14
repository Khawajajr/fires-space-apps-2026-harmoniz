# Handoff

Last updated: 2026-11-14, after the multi-year ingest (09:xx). Read this first, then `CLAUDE.md`.

## Where we are

- The mission brief is `CLAUDE_CODE_PROMPT.md`. The design decisions are in `GLOSSARY.md` and `docs/adr/0001`–`0007`.
- The work plan is `.scratch/space-apps-2026/spec.md`. It includes the agreed **build order and cut order**. The tickets are in `.scratch/space-apps-2026/issues/`, and each says `Status: done` or `ready-for-agent`, with notes at the bottom.
- **Done and pushed:** every ticket (01–13), Phase 7 and Phase 8. Tickets 07 and 08 ran on the global archive on Sat 14 Nov. The user's manual steps are in `FOR_ME_TObeDONE.md`.
- **Any box:** outside the named AOIs the calendar comes from the global 0.25° tiles (2000–2026), built by `ingest-archive`.
- **Data:** MODIS 2000–2011 (12 FIRMS yearly files by country, static-source mask: DATA_CARD) and the 2012–2025 global archive (51 zips in `C:\Users\muham\Downloads\NASA_FIRE_DATA`, read in place) plus 2026 in `data/raw`. `godseye ingest-archive` builds `data/processed/archive/` and `data/processed/aoi/{levant,argentina}/`.
- **Served model:** risk v2.1 (NOAA-20, plus the 2019–2025 climatology feature), calibrated. Test block: ROC-AUC 0.880 vs persistence 0.749 and climatology 0.816 (`docs/MODEL_CARD.md`).

## Things that will bite

- **Archive:**
  - Never extract the zips (~60 GB).
  - Re-running `ingest-archive` skips any zip whose sha256 already has a part in `data/processed/archive/parts/`; the merge alone takes ~30 s.
  - It asserts that the archive never overlaps `data/raw`.
- **The harmonized headline (06) is done:** `src/godseye/calendar/harmonized.py`.
  - Aqua observed is the headline until `observed_until` (2021-12-31); after that, a VIIRS estimate via the links.
  - The `/api/calendar` `harmonized` block carries values, lo, hi, coverage, data_days, estimated_days, substituted_days and caveats.
  - 09 should build climatology on `harmonized.values` per ISO week, using `data_days` to scale or exclude partial weeks and honouring ADR 0006.
  - 08 is done: the switchover figure and the 2013-2021 agreement check are in `reports/figures/headline_switchover.png`.
- **Calendar API shape:** harmonized values go in a new top-level `harmonized` block (values, lo, hi, coverage, provisional). Partial periods carry `data_days`, and climatology (09) must exclude or scale them.
- **Availability:**
  - Statuses are `ok | partial | no_data | not_operational`. `status_own_rule` is the status before the VIIRS cross-sensor check.
  - On 2026 data, S-NPP has 14 outage days and 10 partial days.
  - 2000-2025 availability comes from the archive files, so outages are real global outages (S-NPP 35 no-data days).
- **Servers:**
  - Backend: `python -m godseye api` on :8000. The calendar app is at `/` (and `/app/`), the v0 dashboard at `/legacy/`.
  - Globe: `npm run dev` on :4173.
  - Risk scoring loads in a background thread, so risk endpoints may take ~8 s on the first call.
- **Windows shell:** long Python heredocs with apostrophes break the Bash tool. Write patch scripts to the scratchpad and run those.
- **Contract test:** the 4 v0 endpoints are pinned by `tests/contract/golden.json`. Keep it green.

## Workflow

Each ticket: implement → full `pytest` + `ruff` → two parallel review agents (Standards and Spec, as in the `mattpocock-skills:code-review` skill) → fix → tick the ticket and add notes → append to `docs/CHANGELOG_HACKATHON.md` → commit → push `main`.

## Suggested skills

- `mattpocock-skills:code-review` at the end of each ticket.
- `mattpocock-skills:tdd` at the 4 seams (schema, harmonize, calendar API, risk.evaluate).
- `dataviz` before any chart or UI colour work.
- `mattpocock-skills:diagnosing-bugs` if something breaks.
- `mattpocock-skills:writing-for-agents` when editing `CLAUDE.md`.
