"""Seam 4 (risk.evaluate) and the v2 leakage guards: blocks, labels and features never see past their issue date."""
import numpy as np
import pandas as pd
import pytest

from godseye.config import load_config
from godseye.risk.evaluate import brier, brier_skill, scores
from godseye.risk.v2 import Blocks, PanelV2, check_separation, issue_blocks


def test_scores_match_hand_computed_values():
    y = np.array([0, 0, 1, 1])
    p = np.array([0.1, 0.4, 0.35, 0.8])
    s = scores(y, p, "m", refs={"half": np.full(4, 0.5)})
    assert s["roc_auc"] == 0.75                                   # 3 of 4 positive-negative pairs ordered right
    assert s["brier"] == pytest.approx((0.01 + 0.16 + 0.4225 + 0.04) / 4, abs=1e-4)
    assert s["bss_vs_half"] == pytest.approx(1 - brier(y, p) / 0.25, abs=1e-4)
    assert s["positive_rate"] == 0.5 and s["n"] == 4


def test_brier_skill_signs_and_degenerate_cases():
    y = np.array([1, 0, 1, 0])
    assert brier_skill(y, y.astype(float), np.full(4, 0.5)) == 1.0           # perfect
    assert brier_skill(y, np.full(4, 0.5), np.full(4, 0.5)) == 0.0           # same as reference
    assert brier_skill(y, 1 - y.astype(float), np.full(4, 0.5)) < 0           # worse than reference
    assert brier_skill(y, np.full(4, 0.5), y.astype(float)) is None           # perfect reference: undefined
    one = scores(np.ones(3), np.array([0.2, 0.5, 0.9]), "m")
    assert one["roc_auc"] is None                                            # one class: ROC undefined, not 0.5


def test_configured_blocks_are_separated_by_the_horizon():
    dates = pd.date_range("2026-01-01", "2026-11-06")
    b = issue_blocks(dates, load_config(env={}).risk_v2, horizon=7)
    day = lambda ts: [str(dates[t].date()) for t in (ts[0], ts[-1])]
    assert day(b.train)[1] == "2026-08-21"
    assert day(b.validation) == ["2026-08-28", "2026-09-25"] and day(b.test) == ["2026-10-02", "2026-10-30"]
    assert max(b.train) + 7 <= min(b.validation) and max(b.validation) + 7 <= min(b.test)
    assert max(b.test) + 7 == len(dates) - 1                                 # last label window ends on the last day


@pytest.mark.parametrize("blocks", [
    Blocks([0, 7, 14], [20, 27], [40]),        # train label window (14..21) crosses into validation (20)
    Blocks([0, 7], [14, 21], [25]),            # validation label window (21..28) crosses into test (25)
    Blocks([0, 7], [14, 21], [28, 35]),        # test label window runs past the data
    Blocks([], [14], [28]),                    # empty block
])
def test_leaky_blocks_are_rejected(blocks):
    with pytest.raises(ValueError):
        check_separation(blocks, horizon=7, n_days=40)


def tiny_panel(future_fire: bool = True) -> PanelV2:
    dates = pd.date_range("2026-03-01", periods=60)
    rows = [(dates[d], 31.875, 35.875, 2, 3, 1, 10.0) for d in (5, 6, 40)]
    rows += [(dates[d], 31.875, 36.125, 1, 1, 0, 2.0) for d in (10, 50)] if future_fire else [(dates[10], 31.875,
                                                                                               36.125, 1, 1, 0, 2.0)]
    grid = pd.DataFrame(rows, columns=["acq_date", "cell_lat", "cell_lon", "n_fire_cells", "n_detections",
                                       "n_fire_cells_daytime", "frp_sum_mw"])
    gap = pd.Series(False, index=dates)
    gap.iloc[[20, 21]] = True
    return PanelV2(grid, gap, 0.25, 7)


def test_features_at_t_do_not_see_the_future_and_labels_look_ahead_only():
    a, b = tiny_panel(future_fire=True), tiny_panel(future_fire=False)    # differ only on day 50
    pd.testing.assert_frame_equal(a.features(45), b.features(45))
    t = 45
    lab_a = a.label(t, np.array([0, 1]))
    lab_b = b.label(t, np.array([0, 1]))
    assert lab_a.tolist() == [0, 1] and lab_b.tolist() == [0, 0]            # day 50 is inside t+1..t+7
    with pytest.raises(ValueError):
        a.label(55, np.array([0]))                                           # label window past the data


def test_v2_features():
    p = tiny_panel()
    f = p.features(22).set_index("cell_id")
    assert f.loc[0, "fire_days_30"] == 2 and f.loc[0, "cells_30"] == 4 and f.loc[0, "det_30"] == 6
    assert f.loc[0, "night_share_30"] == pytest.approx(0.5)                   # 2 of 4 fire cells at night
    assert f.loc[0, "days_since_fire"] == 16 and f.loc[0, "nbr_fire_days_30"] == 1   # neighbour burned on day 10
    assert f.loc[0, "gap_days_7"] == 2                                          # NOAA-20 outages on days 20 and 21
    assert "doy_sin" not in f.columns
    assert p.label_window_has_outage(15) and not p.label_window_has_outage(22)
    assert len(p.features(4)) == 0                                              # nothing has burned yet: not scored
