# Live pitch (3 minutes)

Setup before going on stage: run `python -m godseye api`, then open `http://127.0.0.1:8000/#aoi=levant&view=harmonized&unit=week&metric=cell_days`. Optionally run the globe (`cd gods-eye-view; npm run dev`) at `http://localhost:4173/#v=2&lat=32&lon=36&l=w`.

**0:00–0:25 The problem.** Show `reports/figures/headline_switchover.png`.
"NASA has watched fires from space for decades, with two generations of cameras and five satellites in our record since 2000. Follow the red line: in 2012, when the first VIIRS satellite comes online, the count jumps six-fold in the Levant; add NOAA-20 and it jumps again; add NOAA-21, again. None of that is fire. A fire manager in Jordan can't tell whether this season is unusual."

**0:25–1:00 Our method.** Same figure, the green line.
"We count fire cell-days, kilometre cells with any fire, which removes most of the pixel-size difference. Then we map every satellite onto Aqua-MODIS's scale, with links chosen by leave-one-year-out tests over 2013 to 2021: the simplest method the tests can't beat. Regional, monthly ratios cut the error from 24% to 9% against one global ratio, and our 90% bands hold 91 to 92% of the time on years the model never saw. The green line has no jumps."

**1:00–1:50 The product.** Live in the app.
- Levant calendar: "Since 2003, every week on one scale, each with its range. Hover here." (show a tooltip with its 90% range)
- Season panel and unusual weeks: "The season, and the weeks that stood out, like the 2019 wheat-field fires."
- This week vs history: "This week against the same weeks in 14 past years."
- Switch to "By sensor", then Aqua: "Raw sensors are one click away. Aqua's orbit has drifted: our check shows it reading 9.5% low in 2026, so after 2021 the headline comes from VIIRS."
- Hover a hatched or partial week: "Missing data is never zero. Satellite outages are flagged."
- Draw a box anywhere: "Any area works."

**1:50–2:30 Honest forecasting.** Scroll to "Next 7 days".
"A 7-day outlook per quarter-degree cell, calibrated: when it says 30%, about 30% happens. On an October test block it never saw, it ranks fire risk at 0.88, against 0.75 for 'it burned last week' and 0.82 for the 2019–2025 climatology, and it still adds skill where nothing has burned for a month."

**2:30–3:00 Impact and next steps.**
"It's open source, reproducible with one command per step, and built in Amman for the Levant, but it works for any area on Earth. F.I.R.E.S., thank you."

**If something breaks:** the README figures, `docs/MODEL_CARD.md` and the screenshots in `reports/figures/` tell the same story without a live server.
