# 10: This week vs history

**What to build:** A card that tells the user how the current week compares with the same week in every past year, as a percentile plus a plain-language status. Cut candidate #4.

**Blocked by:** 09

**Status:** done

- [x] `GET /api/calendar/now` (pydantic), honouring the ≥5-year rule and coverage gaps
- [x] `web/` card
- [x] Contract tests

## Comments

- `GET /api/calendar/now` (harmonized by default, or `series=<sensor>`):
  - Takes the latest week with enough data (full, or ≥ 5 days scaled to 7).
  - Compares it with the same ISO week ±1 in every other year: percentile (mid-rank) and level (unusually low / below / about / above / unusually high at 10/25/75/90), plus whether the week is in season and a one-sentence summary.
  - Needs ≥ 5 other years, otherwise it returns "needs ≥5 years of history (currently N other year(s))" and still shows this week's value.
- Web: a "This week vs history" card with the level, the sentence, and a p10–p90 bar with this week's marker.
- Also fixed in 09's logic: the incomplete current year now gets anomalies too (scored against the history years).
- Real data: week 45 of 2026, 5 of 7 days, scaled; 0 other years → history message. Synthetic 8 years: "Unusually high, 100th percentile of 7 past years, in season".
- Review fixes:
  - The reference uses the same history years as the climatology (≥ 75% of weeks usable), so `/now` and the panels can't disagree.
  - The sentence counts values and years honestly, with correct ordinals.
  - The harmonized value carries its 90% band, and partial weeks are flagged in the sentence.
  - `data_age_days` is added; the sentence notes data older than 14 days.
  - Week 53 maps to 52 for the season check.
  - The series is computed once per request.
