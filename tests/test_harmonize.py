"""Seam 2: per-sensor series + coefficients in, harmonized series + band out (synthetic series, known answers)."""
import numpy as np
import pandas as pd
import pytest

from godseye.harmonize import validate as V
from godseye.harmonize.link import Link, fit_link, harmonize
from godseye.harmonize.methods import GlobalRatio, QuantileMap, ShrunkRatio
from godseye.harmonize.pipeline import load, save
from godseye.harmonize.series import paired_days, region_of, weekly_pairs

SEASON = dict(zip(range(1, 13), ["DJF", "DJF", "MAM", "MAM", "MAM", "JJA", "JJA", "JJA", "SON", "SON", "SON", "DJF"]))


def synthetic(ratios: dict[str, float], weeks: int = 40, scale: float = 400.0, seed: int = 1) -> pd.DataFrame:
    """Region x week pairs where y = ratio[region] * x plus Poisson noise."""
    rng = np.random.default_rng(seed)
    rows = []
    for w in pd.date_range("2026-01-05", periods=weeks, freq="7D"):
        thursday = w + pd.Timedelta(days=3)
        for region, r in ratios.items():
            x = rng.poisson(scale * (1.5 + np.sin(w.dayofyear / 58)))
            rows.append((region, w, thursday.strftime("%Y-%m"), SEASON[thursday.month], float(x),
                         float(rng.poisson(r * x)), 7))
    return pd.DataFrame(rows, columns=["region", "week", "month", "season", "x", "y", "days"])


def test_global_ratio_recovers_a_known_ratio():
    df = synthetic({"0,30": 0.8, "10,30": 0.8, "-30,-60": 0.8})
    assert GlobalRatio().fit(df).ratio == pytest.approx(0.8, abs=0.01)


def test_shrunk_ratio_recovers_regional_ratios_and_shrinks_sparse_cells_to_the_parent():
    df = synthetic({"0,30": 0.6, "10,30": 1.2})
    sparse = pd.DataFrame([("20,30", df.week.iloc[0], "2026-01", "DJF", 2.0, 4.0, 7)], columns=df.columns)
    model = ShrunkRatio(k=100.0).fit(pd.concat([df, sparse]))
    r = model.ratios(pd.DataFrame({"region": ["0,30", "10,30", "20,30"], "month": ["2026-03"] * 3}))
    assert r[0] == pytest.approx(0.6, abs=0.03) and r[1] == pytest.approx(1.2, abs=0.05)
    # 2 -> 4 alone would say ratio 2; with k=100 it stays near the global ratio
    assert abs(r[2] - model.r_global) < 0.05


def test_quantile_map_matches_distributions():
    df = synthetic({"0,30": 0.5}, weeks=52)
    mapped = QuantileMap(min_n=8).fit(df).predict(df)
    assert mapped.sum() / df.y.sum() == pytest.approx(1.0, abs=0.05)


def test_selection_picks_the_simplest_method_that_is_not_beaten():
    agree = synthetic({"0,30": 1.0, "10,30": 1.0})
    assert V.choose(V.scores(V.cross_validate(agree), V.METHODS)) == "identity"
    offset = synthetic({"0,30": 0.8, "10,30": 0.8})
    assert V.choose(V.scores(V.cross_validate(offset), V.METHODS)) == "global_ratio"


def test_ties_and_near_ties_go_to_the_simpler_method():
    tie = {m: {"region_month_wape": 0.05} for m in V.METHODS}
    assert V.choose(tie) == "identity"
    near = {"identity": {"region_month_wape": 0.0317}, "global_ratio": {"region_month_wape": 0.0312}}
    assert V.choose(near) == "identity"                     # 1.6% better is within noise
    clear = {"identity": {"region_month_wape": 0.0425}, "global_ratio": {"region_month_wape": 0.0326}}
    assert V.choose(clear) == "global_ratio"


def test_fit_link_reports_honest_band_coverage_and_drift():
    link = fit_link(synthetic({"0,30": 0.8, "10,30": 0.8, "-20,20": 0.8}), "A", "B", provisional=True)
    assert link.method == "global_ratio" and link.provisional
    assert 0.80 <= link.report["band_coverage_out_of_fold"] <= 0.98
    lo, mid, hi = link.report["global_ratio_bootstrap_90"]
    assert lo < 0.8 < hi or abs(mid - 0.8) < 0.01
    assert link.report["versus_global_ratio"] == "the chosen method is the global-ratio baseline itself"
    assert {d["month"] for d in link.report["monthly_drift"]} == set(link.report["folds"])


def test_fit_link_refuses_a_method_it_cannot_apply(monkeypatch):
    monkeypatch.setattr(V, "choose", lambda score: "quantile_map_region_season")
    with pytest.raises(NotImplementedError):
        fit_link(synthetic({"0,30": 0.8}), "A", "B", provisional=False)


def link_with(ratio: float) -> Link:
    coef = pd.DataFrame({"level": ["global"], "region": ["*"], "month": [0], "ratio": [ratio]})
    band = pd.DataFrame({"yhat_from": [0.0, 0.0, 100.0], "yhat_to": [0.0, 100.0, np.inf], "n": [30, 50, 50],
                         "lo_factor": [0.0, 0.5, 0.9], "hi_factor": [0.0, 1.5, 1.1], "hi_add": [2.0, 0.0, 0.0]})
    return Link("NOAA-21-VIIRS", "S-NPP-VIIRS", "global_ratio", coef, band, False)


def test_harmonize_applies_the_ratio_and_a_magnitude_dependent_band():
    value, lo, hi = harmonize(np.array([10.0, 1000.0, np.nan, 0.0]), link_with(1.03))
    assert value[:2] == pytest.approx([10.3, 1030.0])
    assert lo[:2] == pytest.approx([5.15, 927.0]) and hi[:2] == pytest.approx([15.45, 1133.0])
    assert np.isnan(value[2]) and np.isnan(lo[2]) and np.isnan(hi[2])     # no data stays no data
    assert (value[3], lo[3], hi[3]) == (0.0, 0.0, 2.0)   # observed zero stays zero, but the other sensor may see some


def test_regional_link_uses_region_month_then_region_then_global():
    coef = pd.DataFrame({"level": ["global", "region", "region_month"], "region": ["*", "0,30", "0,30"],
                         "month": [0, 0, 7], "ratio": [1.0, 0.9, 0.7]})
    link = Link("A", "B", "region_month_shrunk_ratio", coef, link_with(1).band, False)
    regions = np.array(["0,30", "0,30", "50,50"])
    assert link.ratios(regions, np.array([7, 8, 7])).tolist() == [0.7, 0.9, 1.0]
    assert link.ratios(regions, np.array(["2026-07", "2026-08", "2026-07"])).tolist() == [0.7, 0.9, 1.0]


def test_band_factors_never_widen_for_bigger_values():
    rng = np.random.default_rng(0)
    yhat = rng.uniform(0, 2000, 5000)
    y = yhat * rng.lognormal(0, 0.3 / np.sqrt(1 + yhat / 50))
    t = V.band_table(yhat, y).iloc[1:]
    assert (np.diff(t.lo_factor) >= 0).all() and (np.diff(t.hi_factor) <= 0).all()


def test_zero_predictions_get_an_additive_upper_band():
    yhat = np.r_[np.zeros(200), np.full(200, 50.0)]
    y = np.r_[np.r_[np.zeros(180), np.full(20, 4.0)], np.full(200, 50.0)]
    t = V.band_table(yhat, y)
    lo, hi = V.apply_band(np.array([0.0, 50.0]), t)
    assert lo[0] == 0 and hi[0] == pytest.approx(4.0)      # 10% of zero-predicted weeks had 4 cell-days
    assert lo[1] == pytest.approx(50) and hi[1] == pytest.approx(50)


def test_band_table_with_too_little_data_falls_back_to_one_band():
    t = V.band_table(np.array([10.0, 20.0, 30.0]), np.array([9.0, 22.0, 30.0]))
    assert len(t) == 2 and t.yhat_to.iloc[1] == np.inf


def test_save_and_load_round_trip(tmp_path):
    link = fit_link(synthetic({"0,30": 0.8, "10,30": 0.8}), "NOAA-21-VIIRS", "S-NPP-VIIRS", provisional=False)
    save([link], tmp_path, tmp_path / "reports")
    [back] = load(tmp_path)
    assert (back.source, back.method, back.provisional) == ("NOAA-21-VIIRS", "global_ratio", False)
    assert back.ratios() == pytest.approx(link.ratios())
    assert harmonize(np.array([100.0]), back)[0] == pytest.approx(harmonize(np.array([100.0]), link)[0])
    assert (tmp_path / "reports" / "harmonization_report.json").exists()


def test_weekly_pairs_use_only_days_both_sensors_delivered():
    days = pd.date_range("2026-03-02", "2026-03-08")   # one ISO week, Mon..Sun
    grid = pd.DataFrame([(s, d, 31.875, 35.875, 1) for d in days for s in ("NOAA-20-VIIRS", "S-NPP-VIIRS")],
                        columns=["sensor", "acq_date", "cell_lat", "cell_lon", "n_fire_cells"])
    avail = pd.DataFrame([(s, d, "no_data" if (s == "S-NPP-VIIRS" and d.day == 4) else "ok")
                          for d in days for s in ("NOAA-20-VIIRS", "S-NPP-VIIRS")],
                         columns=["sensor", "acq_date", "status"])
    both = paired_days(avail, "NOAA-20-VIIRS", "S-NPP-VIIRS")
    df = weekly_pairs(grid, both, "NOAA-20-VIIRS", "S-NPP-VIIRS", 10.0)
    assert len(both) == 6
    cols = ["region", "x", "y", "month", "season"]
    assert df[cols].values.tolist() == [["30,30", 6.0, 6.0, "2026-03", "MAM"]]   # 6 paired days of 7


def test_region_ids():
    assert region_of(np.array([31.9, -0.1]), np.array([35.9, -179.9]), 10.0).tolist() == ["30,30", "-10,-180"]


def test_caveats_flag_drifting_months_and_provisional_links():
    df = synthetic({"0,30": 0.8, "10,30": 0.8})
    df.loc[df.month == "2026-06", "y"] *= 0.8          # a month where the target sensor read 20% low
    link = fit_link(df, "A", "B", provisional=True)
    assert any(c.startswith("2026-06") for c in link.report["caveats"])
    assert any("provisional" in c for c in link.report["caveats"])
