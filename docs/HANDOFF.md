# Handoff

Last updated: 2026-11-14, before the 09:00 start. Read this first, then `CLAUDE.md`.

## Where we are

- The mission brief is `CLAUDE_CODE_PROMPT.md`. The design decisions are in `GLOSSARY.md` and `docs/adr/0001`–`0007`.
- The work plan is `.scratch/space-apps-2026/spec.md`. It includes the agreed **build order and cut order**. The tickets are in `.scratch/space-apps-2026/issues/`, and each says `Status: done` or `ready-for-agent`, with notes at the bottom.
- **Done and pushed:** tickets 01, 02, 03, 04, 05, 06, 09, 10, 11a, 11b, 12 and 13, plus Phase 7 (docs, CI green, quickstart) and Phase 8 (`docs/SUBMISSION.md`, `docs/DEMO_SCRIPT.md`). See `git log`.
- **Open:** 07 and 08 are coded and tested but need the FIRMS archive files: run the 5 commands in `FOR_ME_TObeDONE.md` §2. The user's manual steps are in the same file.
- **Served model:** risk v2, calibrated. Test block: ROC-AUC 0.867 vs persistence 0.749 (`docs/MODEL_CARD.md`).

## Things that will bite

- **FIRMS archives (2018 → now, Levant + Argentina)** arrive in `C:\Users\muham\Downloads\firms_archive\`.
  - Read them in place; never move or copy them.
  - Ticket 07 runs as soon as files appear. Its notes cover the AOI-basis availability rule and the dedupe against the 2026 files.
  - Hard cutoff for 08: **Sat 14 Nov 18:00 Amman** (ADR 0001).
- **The harmonized headline (06) is done:** `src/godseye/calendar/harmonized.py`.
  - Aqua observed is the headline until `observed_until` (2021-12-31); after that, a VIIRS estimate via the links.
  - The `/api/calendar` `harmonized` block carries values, lo, hi, coverage, data_days, estimated_days, substituted_days and caveats.
  - 09 should build climatology on `harmonized.values` per ISO week, using `data_days` to scale or exclude partial weeks and honouring ADR 0006.
  - 08 still owes the agreement series (story 11) and the switchover figure.
- **Calendar API shape:** harmonized values go in a new top-level `harmonized` block (values, lo, hi, coverage, provisional). Partial periods carry `data_days`, and climatology (09) must exclude or scale them.
- **Availability:**
  - Statuses are `ok | partial | no_data | not_operational`. `status_own_rule` is the status before the VIIRS cross-sensor check.
  - On 2026 data, S-NPP has 14 outage days and 10 partial days.
  - AOI-only archives must not mark zero days as `no_data` (ticket 07 notes).
- **Servers:**
  - Backend: `python -m godseye api` on :8000. The calendar app is at `/app/`, the v0 dashboard at `/`.
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
