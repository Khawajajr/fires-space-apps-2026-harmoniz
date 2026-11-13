# For you to do (Claude worked overnight; this lists what needs a human)

Newest at the bottom of each section. Each item says what to do and how long it takes.

## Decisions (please answer; each has a safe default already in place)

1. **ADR 0006: what counts as an "active" week?** (2 min) See `docs/adr/0006-activity-gate.md`, last paragraph.
   - **Approved now (in use):** a week is active with ≥ 1 fire cell-day. Problem: in a big area, stray winter detections make *every* week active, so the "critical period" becomes the whole year. A test on synthetic 8-year data shows this.
   - **Proposed:** a week is active when it reaches 10% of the area's own peak weekly median (never below 1). It's scale-invariant and matches the usual fire-season definitions.
   - **To accept:** in `configs/pipeline.yaml` set `climatology: activity: relative`, then change the ADR's "PROPOSED" to "ACCEPTED". Nothing else is needed. To reject, leave it as it is.
   - With today's 2026-only data this changes nothing visible: the panels say "needs ≥5 years of history".

## Data

2. **FIRMS archive downloads (2018 → now, Levant + Argentina).** Put the files (zips or CSVs, as delivered) in `C:\Users\muham\Downloads\firms_archive\`. Claude reads them in place.
   - A watcher is running, and ticket 07 starts as soon as files appear.
   - Hard cutoff for the 2018–2021 calibration: **Sat 14 Nov 18:00 Amman**. After that, the provisional 2026 calibration and the fallback figure ship (already built).

## Accounts / submission (Claude can't do these)

3. **Space Apps project page.** Register the team "Space Jo" with all 5 members on the Members tab; select the challenge "Harmonization of MODIS and VIIRS Hot Spots"; event Amman. The drafts for every field come in `docs/SUBMISSION.md` (Phase 8).
4. **Public repo before submission.** `Khawajajr/fires-space-apps-2026` is **private**. The judges need a public link: on GitHub, Settings → Change visibility → Public (or tell Claude to do it with `gh repo edit --visibility public --accept-visibility-change-consequences`). Do this after the secret scan in Phase 7.
