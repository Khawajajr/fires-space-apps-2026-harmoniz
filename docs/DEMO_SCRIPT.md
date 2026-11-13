# Live pitch (3 minutes)

Setup before going on stage: run `python -m godseye api`, then open `http://127.0.0.1:8000/app/#aoi=levant&view=harmonized&unit=week&metric=cell_days`. Optionally run the globe (`cd gods-eye-view; npm run dev`) at `http://localhost:4173/#v=2&lat=32&lon=36&l=w`.

**0:00–0:25 The problem.** Show `reports/figures/headline_same_fires_different_camera.png`, left panel.
"NASA has watched fires from space since 2000, but with two generations of cameras. VIIRS sees four to seven times more fire than MODIS. Put them on one chart and you get a jump that is the satellite, not the fire. A fire manager in Jordan can't tell whether this season is unusual."

**0:25–1:00 Our method.** Same figure, right panel.
"We count fire cell-days, kilometre cells with any fire, which removes most of the pixel-size difference. We then map VIIRS onto MODIS Aqua's scale with links chosen by out-of-sample tests: the simplest method that the tests can't beat. On weeks the model never saw, our estimate lands at 1.03 times what Aqua saw over the Levant and 0.96 over Argentina, inside our 90% band 93 to 98% of the time."

**1:00–1:50 The product.** Live in the app.
- Levant calendar: "Every week on one scale, each with its range. Hover here." (show a tooltip with its 90% range)
- Switch to "By sensor", then Aqua: "Raw sensors are one click away. Aqua's orbit has drifted to 15:24, which we measured from the data, so after 2021 the headline comes from VIIRS."
- Hover a hatched or partial week: "Missing data is never zero. The S-NPP satellite had 14 outage days this year, and we flag them."
- Draw a box anywhere: "Any area works."

**1:50–2:30 Honest forecasting.** Scroll to "Next 7 days".
"A 7-day outlook per quarter-degree cell, calibrated: when it says 30%, about 30% happens. On an October test block it never saw, it ranks fire risk at 0.867 against 0.749 for 'it burned last week', and it still adds skill where nothing has burned for a month."

**2:30–3:00 Impact and next steps.**
"With the 2018–2021 archive, the calendar's season and anomaly panels switch on, and the provisional label goes. It's open source, reproducible with one command per step, and built in Amman for the Levant, but it works for any area on Earth. F.I.R.E.S., thank you."

**If something breaks:** the README figures, `docs/MODEL_CARD.md` and the screenshots in `reports/figures/` tell the same story without a live server.
