# 08: 2013–2021 Aqua ↔ S-NPP calibration + 2012-jump figure

**What to build:** The final VIIRS → Aqua-equivalent link, fitted on 2013–2021, replaces the provisional one. The record is assembled per ADR 0001, and the headline "2012 jump removed" figure is produced.

**Blocked by:** 06, 07. **Cutoff Sat 14 Nov 18:00 (Amman):** if the archives aren't ingested by then, close this ticket as "cut". 06's provisional link and fallback figure ship instead.

**Status:** ready-for-agent

- [ ] 3 candidates, leave-one-year-out; 90% band from bootstrapping over years; drift check on 2022–2026
- [ ] Record segments:
  - Terra-only flagged "not comparable (morning orbit)";
  - Aqua observed 2002–2021 as the headline, with S-NPP Aqua-equivalent overlaid from 2012;
  - VIIRS Aqua-equivalent as the headline from 2022, with Aqua labelled "drifting orbit".
- [ ] Headline figure (raw MODIS+VIIRS showing the 2012 jump, vs harmonized + band) for Levant and Argentina, replacing the 06 fallback
- [ ] The harmonization validation notebook runs top to bottom; report `provisional: false`
