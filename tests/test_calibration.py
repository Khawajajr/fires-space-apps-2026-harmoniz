"""Isotonic calibration and reliability tables (11b)."""
import numpy as np
import pytest

from godseye.risk.calibration import isotonic_apply, isotonic_fit, reliability


def test_isotonic_fixes_an_overconfident_model_and_stays_monotone():
    rng = np.random.default_rng(0)
    true = rng.uniform(0, 1, 20000)
    y = (rng.uniform(0, 1, 20000) < true).astype(int)
    p = np.clip(true ** 0.5, 0, 1)                         # overconfident
    bp = isotonic_fit(p, y)
    assert all(a <= b for a, b in zip(bp[1], bp[1][1:]))   # monotone
    cal = isotonic_apply(p, bp)
    before = [abs(b["mean_predicted"] - b["observed_rate"]) for b in reliability(y, p)]
    after = [abs(b["mean_predicted"] - b["observed_rate"]) for b in reliability(y, cal)]
    assert max(after) < 0.05 < max(before)


def test_reliability_bins():
    r = reliability(np.array([0, 1, 1, 0]), np.array([0.05, 0.95, 0.91, 0.12]))
    assert [b["bin"] for b in r] == ["0.0-0.1", "0.1-0.2", "0.9-1.0"]
    assert r[-1]["observed_rate"] == 1.0 and r[-1]["n"] == 2
    assert r[-1]["mean_predicted"] == pytest.approx(0.93)
