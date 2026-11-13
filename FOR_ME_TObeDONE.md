# For you to do (Claude worked overnight; this lists what needs a human)

Updated 2026-11-14, early morning. Everything Claude could do is done and pushed: all tickets except 07/08, which wait for the archive files. CI is green, the docs and the submission drafts are written. What's left needs you.

## 1. Decide (2 min)

**ADR 0006: what counts as an "active" week?** See `docs/adr/0006-activity-gate.md`, last paragraph.
- **In use now (as approved):** active = ≥ 1 fire cell-day. In a big area, stray winter detections make every week active, so the "critical period" becomes the whole year. A synthetic 8-year test shows this.
- **Proposed:** active = 10% of the area's own peak weekly median (never below 1). It's scale-invariant and follows the usual fire-season definitions.
- **To accept:** in `configs/pipeline.yaml` set `climatology: activity: relative` and change "PROPOSED" to "ACCEPTED" in the ADR. To reject, do nothing.
- It only matters once there are ≥ 5 years of data.

## 2. Data (as soon as possible: hard cutoff Sat 14 Nov 18:00 Amman)

Put the FIRMS archive files (zips or CSVs, as delivered) in `C:\Users\muham\Downloads\firms_archive\`. The code for tickets 07 and 08 is done and tested; it only needs running. Ask Claude, or run it yourself (about 10–20 minutes):

```
.venv\Scripts\python -m godseye ingest --aoi levant
.venv\Scripts\python -m godseye ingest --aoi argentina
.venv\Scripts\python -m godseye harmonize          # refits the headline link on 2018-2021; writes headline_switchover.png
.venv\Scripts\python -m godseye manifest data\raw C:\Users\muham\Downloads\firms_archive
.venv\Scripts\python -m godseye api                # restart; Levant/Jordan/Argentina now show 2018-2026
```

Then swap the README hero image to `reports/figures/headline_switchover.png` and update its caption with the numbers from `reports/harmonization_report.json`.
- **With them:** the 2018–2021 stable-orbit calibration replaces the provisional one, the calendar gets 9 years, the season, anomaly and "this week vs history" panels switch on, and the headline figure becomes the "simulated switchover".
- **Without them:** the provisional version ships. It is fully built and honest.

## 3. Before submitting (Sun 15 Nov, aim for 20:00)

1. **Make the repo public** (the judges need the link): `gh repo edit Khawajajr/fires-space-apps-2026 --visibility public --accept-visibility-change-consequences`. The secret scan was clean. The globe fork `Khawajajr/gods-eye-view` is already public.
2. **Space Apps project page:**
   - add all 5 members to the Members tab;
   - select the challenge "Harmonization of MODIS and VIIRS Hot Spots";
   - paste the fields from `docs/SUBMISSION.md`.
3. **Demo:** record the ≤30-second video (shot list in `docs/SUBMISSION.md`, option A) **or** make the ≤7 slides (option B).
   - The screenshots are in `reports/figures/`.
   - For live screenshots: `.venv\Scripts\python -m godseye api`, then open `http://127.0.0.1:8000/app/`.
4. **Live pitch:** rehearse `docs/DEMO_SCRIPT.md` (3 min).
5. **Challenge link:** add the exact Space Apps challenge URL to the top of `README.md` (Claude didn't guess it).

## 4. Nice to have (only if time remains)

- Per-cell "why" for the risk forecast (`pred_contrib` in the Next 7 days panel): cut candidate #2, not done.
- Arabic UI strings (the brief calls this a bonus).
- Make the calendar app the default page at `/` (now `/app/`; `/` is the v0 dashboard).
