# For you to do

Updated 2026-11-14, ~09:15 Amman. The archive ingest, the multi-year calibration and risk v2.1 are done and pushed. CI-equivalent checks (ruff + full pytest) pass locally. What's left needs you.

## 1. Check first (5 min): work done before the start

`docs/SUBMISSION.md` → "What existed before the start" states plainly that **almost all of the project was built before Sat 09:00**, during the pre-event preparation (Fri 22:19 → Sat 08:59; the last pre-start commit `aad486f` is tagged `event-start`). Please check the Space Apps rules for your local event on pre-existing work, and adjust the wording with your organisers if needed. Claude did not interpret the rules.

## 2. Decisions already applied (just so you know)

- **ADR 0006:** the relative active-week rule is ACCEPTED, as you instructed, before any multi-year data was merged; the ADR says so.
- **Consequence, reported as is:** under that rule (fixed in advance), Argentina and Jordan count as active all 52 weeks, so their "critical period" is the whole year. The Levant's is 45 weeks. Jordan averages 2.9 fire cell-days/week (above the "too little activity" floor of 1).
- **Risk:** v2.1 kept by the pre-declared validation rule (Brier 0.0906 vs 0.0929) and served; the model card reports both.

## 3. Before submitting (Sun 15 Nov, aim for 20:00)

1. **Make the repo public** (the judges need the link): `gh repo edit Khawajajr/fires-space-apps-2026 --visibility public --accept-visibility-change-consequences`. The globe fork `Khawajajr/gods-eye-view` is already public.
2. **Space Apps project page:**
   - add all 5 members to the Members tab;
   - select the challenge "Harmonization of MODIS and VIIRS Hot Spots";
   - paste the fields from `docs/SUBMISSION.md`.
3. **Demo:** record the ≤30-second video (shot list in `docs/SUBMISSION.md`, option A) **or** make the ≤7 slides (option B; the slide table is in the same file).
   - Figures and screenshots: `reports/figures/headline_switchover.png`, `app_calendar_{levant,jordan,argentina}.png`, `risk_reliability.png`.
   - For live screenshots: `.venv\Scripts\python -m godseye api`, then open `http://127.0.0.1:8000/` (add `#aoi=jordan` etc.).
4. **Live pitch:** rehearse `docs/DEMO_SCRIPT.md` (3 min).
5. **Challenge link:** add the exact Space Apps challenge URL to the top of `README.md` (Claude didn't guess it).

## 4. Still open from your list

- Done: the 2026 Aqua NRT check, the "active all year" message, the two focused areas (ADR 0008) and the Arabic UI. A native Arabic speaker on the team should proofread `web/i18n/strings.json` ("ar" block) before the demo.

## 5. Nice to have (only if time remains)

- Per-cell "why" for the risk forecast (`pred_contrib` in the Next 7 days panel): cut candidate #2, not done.
- Push the CI run: the last local full test run passed; check the GitHub Actions badge after the push.
