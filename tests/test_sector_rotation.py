import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research"))
from sector_rotation import ASSETS, simulate, targets


class SectorTests(unittest.TestCase):
    def test_current_month_does_not_change_target_at_its_open(self):
        days = pd.bdate_range("2000-01-01", periods=540)
        prices = pd.DataFrame(np.exp(np.arange(len(days))[:, None] *
                                     np.linspace(.0002, .001, len(ASSETS))), index=days, columns=ASSETS)
        day = pd.Timestamp("2001-12-03")
        altered = prices.copy()
        altered.loc[day:, "SPY"] *= 5
        for mode in ("rotation", "breadth"):
            original = targets(prices, mode).loc[day]
            pd.testing.assert_series_equal(original, targets(altered, mode).loc[day])
            pd.testing.assert_series_equal(original, targets(prices.loc[:day], mode).loc[day])
        self.assertAlmostEqual(targets(prices).loc[day, "SPY"], .75)

    def test_overnight_gain_belongs_to_previous_holding(self):
        days = pd.date_range("2020-01-01", periods=2)
        prices = pd.DataFrame([[10., 10.], [20., 30.]], index=days)
        schedule = pd.DataFrame([[1., 0.], [0., .5]], index=days)
        r = simulate(prices, prices, schedule, .01, start=days[0])
        # First purchase, overnight doubling, sale, half position in the second asset,
        # then liquidation of that position only.
        expected = (2 / 1.01) * .99 / 1.005 * .995
        self.assertAlmostEqual((1 + r).prod(), expected)
