import unittest
import sys
from pathlib import Path
import numpy as np
import pandas as pd
from quantbot.strategy import targets
from quantbot.ledger import replay
RESEARCH=Path(__file__).resolve().parents[1]/'research'
sys.path.insert(0,str(RESEARCH))
from iteration_03 import candidates
from audit_backtests import simulate
from quantbot.data import validate

class ReferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d=pd.read_csv(RESEARCH/'btcusdt_spot_4h.csv',parse_dates=['open_time']).set_index('open_time').sort_index()
        cls.d.index=pd.to_datetime(cls.d.index,utc=True)
        cls.d=cls.d.loc[cls.d.index<'2026-11-06']
    def test_signals_match_frozen_research(self):
        np.testing.assert_allclose(targets(self.d),candidates(self.d)['confirm3_vol0.3'])
    def test_no_future_leakage(self):
        cut=len(self.d)//2; changed=self.d.copy();changed.iloc[cut:,changed.columns.get_indexer(['open','high','low','close'])]*=1.5
        np.testing.assert_allclose(targets(self.d).iloc[:cut],targets(changed).iloc[:cut])
    def test_ledger_reconciles(self):
        d=self.d.loc[(self.d.index>='2023-01-01')&(self.d.index<'2024-01-01')]
        t=targets(self.d).shift(1).reindex(d.index).fillna(0.)
        # replay shifts internally, retain one prior bar so first target is aligned.
        prev=self.d.loc[self.d.index<d.index[0]].iloc[-1:]; window=pd.concat([prev,d]); target=targets(self.d).reindex(window.index)
        marks,orders=replay(window,target)
        self.assertTrue(np.all(marks.cash>=-1e-9));self.assertTrue(np.all(marks.units>=-1e-9))
        self.assertTrue(np.allclose(marks.equity,marks.cash+marks.units*marks.close))
        self.assertGreater(len(orders),0)
    def test_flat_roundtrip(self):
        idx=pd.date_range('2024-01-01',periods=5,freq='4h',tz='UTC'); d=pd.DataFrame({'open':100.,'close':100.},index=idx)
        marks,orders=replay(d,pd.Series([1.,1.,0.,0.,0.],index=idx),fee=.01)
        self.assertAlmostEqual(marks.equity.iloc[-1],.99/1.01)
        self.assertEqual(list(orders.side),['buy','sell'])
    def test_replay_matches_audited_terminal_equity(self):
        target=targets(self.d)
        marks,_=replay(self.d,target,fee=.0015)
        after_exit=marks.equity.iloc[-1]-marks.units.iloc[-1]*marks.close.iloc[-1]*.0015
        audited,_,_=simulate(self.d,target,'2020-01-01','2026-11-06',cost=.0015)
        self.assertAlmostEqual(after_exit,float((1+audited).prod()),places=9)
    def test_period_start_preserves_previous_signal(self):
        idx=pd.date_range('2024-01-01',periods=3,freq='4h',tz='UTC'); d=pd.DataFrame({'open':100.,'close':100.},index=idx)
        marks,orders=replay(d,pd.Series(1.,index=idx),fee=0.,prior_target=1.)
        self.assertEqual(orders.iloc[0]['time'],idx[0]);self.assertAlmostEqual(marks.units.iloc[0],.01)
    def test_bad_ohlc_and_gap(self):
        d=self.d.iloc[:4].copy();d.iloc[0,d.columns.get_loc('low')]=d.iloc[0]['high']+1
        with self.assertRaises(ValueError):validate(d)
        d=self.d.iloc[[0,1,3]].copy();self.assertEqual(len(validate(d)),1)

if __name__=='__main__':unittest.main()
