# Handoff

Last updated: 2026-11-14 ~14:10 Amman, end of day 1. Read this first, then `CLAUDE.md`.

## Where we are

- **Everything is committed and pushed**, and CI is green.
  - This repo: `main` at `5fa9029`.
  - The globe fork (`gods-eye-view`, branch `space-apps-2026`): `09b62da7`.
- The mission brief is `CLAUDE_CODE_PROMPT.md`. Design decisions are in `GLOSSARY.md` and `docs/adr/0001`–`0008`. The work log, with times, is in `docs/CHANGELOG_HACKATHON.md`: everything after commit `aad486f` (tag `event-start`) is during-event work.
- **Data:**
  - MODIS 2000–2011: the 12 FIRMS yearly files by country, with the static-source mask (see DATA_CARD).
  - The 2012–2025 global archive. All 51 zips are in `C:\Users\muham\Downloads\NASA_FIRE_DATA` and are read in place.
  - 2026 in `data/raw`, including the public 7-day NRT files in `FIRMS_NRT_7d_20261114/`. The data runs to 14 Nov ~04:16 UTC, and 14 Nov is partial.
- **Record:**
  - The Aqua-equivalent headline runs 2003–2026: Aqua observed to 2021, then VIIRS mapped to Aqua.
  - Terra and 2000–2002 appear in "By sensor" only, because the Terra → Aqua link failed a held-out rule fixed in advance (`reports/terra_aqua_link_test.json`).
  - The headline figure shows the real January 2012 switch.
- **Named areas and their critical periods (ADR 0006):**
  - Levant: 5 May – 2 Mar, 43 weeks.
  - Jordan, Argentina and the Paraná Delta: active all year.
  - Northern Jordan forest belt: too little activity.
  - Any drawn box gets 2003–2026 history from the global 0.25° tiles.
- **App:**
  - `http://127.0.0.1:8000/` has an EN / عربي toggle.
  - The served model is risk v2.1 (test ROC-AUC 0.880 vs persistence 0.749 and climatology 0.816).
  - The forecast was issued 13 Nov and is valid to 20 Nov.
- **Static snapshot:** `site/`, built 14 Nov 13:53 (289 JSON answers, English and Arabic, 22 MB). It is **not published**, and the repo is still private.

## Tomorrow (Sun 15 Nov): plan, in order

Hard deadline: **submit by 20:00 Amman** (the event closes 23:59). Keep the before/after-09:00 split honest in SUBMISSION and the changelog.

1. **NRT refresh, first thing (~20 min, mostly waiting):**
   - Download the three public FIRMS global 7-day CSVs into a new folder `data/raw/FIRMS_NRT_7d_20261115/`:
     - `https://firms.modaps.eosdis.nasa.gov/data/active_fire/modis-c6.1/csv/MODIS_C6_1_Global_7d.csv`
     - `.../noaa-20-viirs-c2/csv/J1_VIIRS_C2_Global_7d.csv`
     - `.../noaa-21-viirs-c2/csv/J2_VIIRS_C2_Global_7d.csv`
   - **Keep the 20261114 folder.** It holds 7 Nov. The overlap is removed by clean's duplicate check (satellite, time, lat, lon, over the whole table), so check `dropped_duplicates` in `data/processed/cleaning_report.json` is roughly the overlapping rows.
   - Then, in order:
     - `python -m godseye manifest`
     - `python -m godseye clean` (~9 min)
     - `python -m godseye aggregate`
     - `python -m godseye ingest-archive`, which reads no zips and only runs the merge (~3 min)
     - restart the API. The risk forecast rescores itself in the background, because its cache is keyed by the data files.
   - Check:
     - `/api/meta` last day;
     - "This week" (week 46 completes on 15 Nov, so week 47 may start);
     - the forecast issue date is the last full NOAA-20 day.
   - Run the full `pytest`. If the contract test fails only on "recent fires", re-capture the golden from `v0-prototype` as in the 10:35 changelog entry.
   - Log it in the changelog.
2. **Rebuild `site/`** after the refresh: run `python -m godseye build-site` (20 s). Test it with `python -m http.server -d site 8090`, checking the Levant, Arabic and a drawn box. Commit and push.
3. **Publish decision (the team decides; nothing is published yet):**
   - **Option a:** make `Khawajajr/fires-space-apps-2026` public and enable GitHub Pages from `main` / `site/`. `site/.nojekyll` is already there.
   - **Option b:** push only `site/` to a new public repo and enable Pages there.
   - **Either way:**
     - check that no data, models or secrets are tracked (`git ls-files | grep -E "data/|models/"` should list only READMEs, `data/manifest.json` and model metadata);
     - open the published URL from another device;
     - put the URL in SUBMISSION and the README.
4. **Demo:**
   - Choose the ≤30 s video or the ≤7 slides (`docs/SUBMISSION.md` has the shot list and the slide table, updated to 2000–2026; `docs/DEMO_SCRIPT.md` has the 3-minute live pitch).
   - Rehearse with the live app and the snapshot as the fallback.
   - A native Arabic speaker should proofread the "ar" block of `web/i18n/strings.json`.
5. **Submit by 20:00:**
   - Project page with all 5 members and the challenge "Harmonization of MODIS and VIIRS Hot Spots".
   - Public repo link, demo link and references (copied from `docs/REFERENCES.md`).
   - Use the final checklist at the end of `docs/SUBMISSION.md` and `FOR_ME_TObeDONE.md`.
   - Check the event rules on pre-start work: the SUBMISSION section "What existed before the start" states it plainly.

## Things that will bite

- **Archive:**
  - Never extract the zips (~60 GB).
  - `ingest-archive` skips any zip whose sha256 already has a part in `data/processed/archive/parts/`, so a re-run is just the merge.
  - It asserts that the archive never overlaps `data/raw`.
  - Country-file zips (`*_all_countries.zip`) get the static-source mask, which is cached in `data/processed/archive/static_mask_modis.*`.
- **Headline config** (`configs/pipeline.yaml`, `harmonize.headline`):
  - `observed_from: 2003-01-01`;
  - `observed_until: 2021-12-31`;
  - `switch_after: 2011` (the figure only).
  - The VIIRS links and the 2013–2021 window are fixed: don't refit them for the deadline.
- **Availability:** statuses are `ok | partial | no_data | not_operational`. Gaps are "no data", never zero.
- **Servers** (all stopped at the end of day 1):
  - Backend: `.venv\Scripts\python -m godseye api` on :8000. The calendar app is at `/`, the v0 dashboard at `/legacy/`.
  - Globe: `cd gods-eye-view; npm run dev` on :4173 (needs `GODS_EYE_API_URL=http://127.0.0.1:8000`).
  - Snapshot: `python -m http.server -d site 8090`.
  - The API holds ~2.5 GB with tiles cached. Stop it before `ingest-archive`'s merge rewrites the tiles.
- **Snapshot:** `web/snapshot.js` is loaded only in `site/` (the builder injects it). Two strings are shared through `ui.snapshot.*` in `strings.json`.
- **Windows shell:**
  - Bash heredocs mangle `→`, en dashes and Arabic. Use the Edit tool, or write a script to the scratchpad.
  - Headless Chrome screenshots need absolute Windows paths and one Chrome call per command.
  - Don't name a scratch script after a standard-library module (a `numbers.py` broke numpy today).
- **Contract test:** the 4 v0 endpoints are pinned by `tests/contract/golden.json`. It is skipped while a newer risk model is served, and the schema test still runs.

## Workflow

Each change: implement → full `pytest` + `ruff` → append to `docs/CHANGELOG_HACKATHON.md` (during-event, with the time) → commit (never data or model binaries) → push `main` (never force-push).

## Suggested skills

- `mattpocock-skills:code-review` before the final push.
- `dataviz` before any chart or UI colour work.
- `mattpocock-skills:diagnosing-bugs` if something breaks.
