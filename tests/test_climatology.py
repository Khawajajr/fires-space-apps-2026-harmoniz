"""Climatology, ADR 0006 activity gate, anomalies and critical periods on synthetic multi-year weekly series."""
import numpy as np
import pytest

from godseye.calendar.climatology import analyse, usable

YEARS = list(range(2018, 2026))


def grid(fn, years=YEARS, seed=0):
    """years x 53 weekly values from fn(year, week_index, rng); week 53 absent; full coverage, 7 data days."""
    rng = np.random.default_rng(seed)
    v = np.array([[fn(y, w, rng) for w in range(53)] for y in years], dtype=float)
    cov = np.full(v.shape, "full", dtype=object)
    cov[:, 52] = "absent"
    v[:, 52] = np.nan
    return v, cov.astype(str), np.full(v.shape, 7)


def summer_season(y, w, rng):
    if 19 <= w <= 33:                    # ISO weeks 20-34
        return 100 + rng.normal(0, 10)
    return rng.choice([0.0, 0.0, 0.0, 0.5])


def test_too_few_years_gives_the_history_message():
    v, cov, days = grid(summer_season, years=[2024, 2025, 2026])
    a = analyse([2024, 2025, 2026], v, cov, days)
    assert a.status == "insufficient_history" and a.message == "needs ≥5 years of history (currently 3)"
    assert a.climatology == [] and a.critical_periods == [] and a.anomalies == []


def test_default_gate_finds_the_season_as_one_critical_period():
    v, cov, days = grid(summer_season)
    a = analyse(YEARS, v, cov, days)
    assert a.status == "ok" and a.gate_rule == "default"
    assert 19 in a.gated_weeks and 35 in a.gated_weeks and 1 not in a.gated_weeks   # +-1 week pooling
    [top, *_] = a.critical_periods
    assert (top["rank"], top["start_week"], top["end_week"]) == (1, 19, 35)
    assert top["share_of_year"] > 0.95
    week27 = a.climatology[26]
    assert 85 < week27["median"] < 115 and week27["p_active"] == 1.0


def test_an_unusual_week_is_found_against_a_climatology_without_its_own_year():
    v, cov, days = grid(summer_season)
    v[YEARS.index(2023), 29] = 400                     # ISO week 30 of 2023
    a = analyse(YEARS, v, cov, days)
    assert a.anomalies[0]["year"] == 2023 and a.anomalies[0]["week"] == 30 and a.anomalies[0]["z"] > 5
    assert all(an["week"] in a.gated_weeks for an in a.anomalies)       # off-season noise never flagged


def test_short_season_switches_to_the_relative_gate():
    def short(y, w, rng):
        return 30.0 if w in (29, 30) else 0.0          # two weeks a year
    v, cov, days = grid(short)
    a = analyse(YEARS, v, cov, days)
    assert a.gate_rule == "relative"
    assert set(a.gated_weeks) == {29, 30, 31, 32}      # the weeks that ever see activity (with pooling)


def test_sparse_area_hits_the_floor_no_critical_periods_but_still_anomalies():
    def sparse(y, w, rng):
        return 0.0
    v, cov, days = grid(sparse)
    v[YEARS.index(2021), 10] = 6.0
    a = analyse(YEARS, v, cov, days)
    assert a.gate_rule == "floor" and a.critical_periods == []
    assert a.message == "too little detected activity to define critical periods"
    assert [(x["year"], x["week"]) for x in a.anomalies] == [(2021, 11)]


def test_a_southern_season_across_new_year_is_one_period():
    def wrap(y, w, rng):
        return 80.0 if (w >= 47 or w <= 4) else 0.0     # ISO weeks 48-52 and 1-5
    v, cov, days = grid(wrap)
    a = analyse(YEARS, v, cov, days)
    top = a.critical_periods[0]
    assert top["start_week"] > top["end_week"] and len(a.critical_periods) == 1


def test_partial_weeks_are_scaled_or_left_out_never_zero():
    v = np.array([[70.0, 60.0, 30.0, 5.0]])
    cov = np.array([["full", "partial", "partial", "none"]])
    days = np.array([[7, 6, 3, 0]])
    u = usable(v, cov, days)
    assert u[0, 0] == 70 and u[0, 1] == pytest.approx(70) and np.isnan(u[0, 2]) and np.isnan(u[0, 3])


def test_a_partial_current_year_still_counts_as_history_when_mostly_covered():
    v, cov, days = grid(summer_season, years=list(range(2018, 2023)))
    v[-1, 45:52] = np.nan
    cov[-1, 45:52] = "none"                            # last 7 weeks missing: 45/52 usable
    a = analyse(list(range(2018, 2023)), v, cov, days)
    assert a.history_years == list(range(2018, 2023)) and a.status == "ok"


def test_relative_gate_takes_exactly_the_top_share_even_with_ties():
    def flat_short(y, w, rng):
        return 30.0 if w < 20 else 0.0                 # 20 active weeks
    v, cov, days = grid(flat_short)
    a = analyse(YEARS, v, cov, days)
    assert a.gate_rule == "default"                    # 20+ active weeks: default rule
    def tiny(y, w, rng):
        return 60.0 if w in (10, 11, 12) and y % 2 else 0.0      # mean ~1.7 a week: above the floor
    v, cov, days = grid(tiny)
    a = analyse(YEARS, v, cov, days)
    assert a.gate_rule == "relative" and len(a.gated_weeks) <= 11
    assert a.gate_counts["relative_rule_weeks"] == len(a.gated_weeks)


def test_week_reference_and_percentile_for_this_week_vs_history():
    from godseye.calendar.climatology import percentile_of, week_reference
    v, cov, days = grid(summer_season)
    ref = week_reference(YEARS, v, cov, days, week=27, exclude_year=2025)
    assert len(ref) == 3 * 7                           # 7 other years x 3 pooled weeks
    assert percentile_of(400.0, ref) == 100.0 and percentile_of(0.0, ref) == 0.0
    assert percentile_of(float(np.median(ref)), ref) == pytest.approx(50, abs=5)
    assert percentile_of(np.nan, ref) is None


def test_relative_activity_mode_is_scale_invariant():
    v, cov, days = grid(summer_season)
    big = analyse(YEARS, v * 50, cov, days, activity="relative")
    small = analyse(YEARS, v, cov, days, activity="relative")
    assert big.gated_weeks == small.gated_weeks and big.active_threshold == pytest.approx(50 * small.active_threshold,
                                                                                         rel=0.01)
