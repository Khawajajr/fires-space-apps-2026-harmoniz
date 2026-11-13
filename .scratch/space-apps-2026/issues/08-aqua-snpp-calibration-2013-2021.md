# 08: Aqua ↔ S-NPP calibration on the pre-drift window + switchover figure

**What to build:** The final VIIRS → Aqua-equivalent link replaces the provisional one. It is fitted on the pre-drift calibration window: **2018–2021** with the current archives, extended automatically to **2013–2021** if pre-2018 years arrive. The record is assembled per ADR 0001, and the headline switchover figure is produced.

**Blocked by:** 06, 07. **Cutoff Sat 14 Nov 18:00 (Amman):** if the archives aren't ingested by then, close this ticket as "cut"; 06's provisional link and fallback figure ship instead.

**Status:** ready-for-agent

- [ ] Calibration window chosen from the data: the overlap years ≤ 2021 that both Aqua and S-NPP cover (2018–2021 now; 2013–2021 if early years exist). The window used is recorded in the report.
- [ ] 3 candidates, leave-one-year-out over the window's years (4 now); 90% band from bootstrapping over years. The band will be wider with 4 years; report it as it is.
- [ ] Drift check on 2022–2026 (Aqua observed vs harmonized VIIRS)
- [ ] Record segments: Aqua observed as the headline through 2021, with S-NPP Aqua-equivalent overlaid; VIIRS Aqua-equivalent as the headline from 2022, with Aqua labelled "drifting orbit". The Terra-only segment appears only if 2000–2002 data exists.
- [ ] **Headline figure** for Levant and Argentina:
  - Until pre-2018 data exists: a clearly labelled **"simulated sensor switchover"**. Raw MODIS-only 2018–2021, then raw VIIRS-only 2022–2025, showing the artificial jump, next to the harmonized Aqua-equivalent series (no jump, with its band).
  - If the early years arrive: the real 2012 transition replaces it.
  - Either way, it replaces the 06 fallback.
- [ ] The harmonization validation notebook runs top to bottom; report `provisional: false`
