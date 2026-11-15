import sys
import unittest
from pathlib import Path
import numpy as np
import pandas as pd

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'research'))
from backtest_spy import signal,simulate

class SpyTests(unittest.TestCase):
    def test_flat_price_round_trip_cost(self):
        idx=pd.bdate_range('2020-01-01',periods=6)
        d=pd.DataFrame({'open':100.,'close':100.},index=idx)
        raw=pd.Series([1.,1.,0.,0.,0.,0.],index=idx)
        r,orders,_=simulate(d,raw,'2020-01-01','2020-02-01',fee=.01)
        self.assertAlmostEqual((1+r).prod(),.99/1.01)
        self.assertEqual(orders,2)

    def test_future_prices_do_not_change_prior_signal(self):
        idx=pd.bdate_range('2020-01-01',periods=100)
        c=100+np.arange(len(idx))*.2+np.sin(np.arange(len(idx)))
        d=pd.DataFrame({'close':c},index=idx); altered=d.copy();altered.iloc[70:]*=2
        np.testing.assert_allclose(signal(d).iloc[:70],signal(altered).iloc[:70])

if __name__=='__main__':unittest.main()
