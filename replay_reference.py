"""Offline replay of the frozen BTC/ETH candidate; generates local CSVs only."""
from pathlib import Path
import argparse
import pandas as pd
from quantbot.data import validate
from quantbot.strategy import targets
from quantbot.ledger import replay

DATA_DIR=Path(__file__).resolve().parent/'research'

def main():
    p=argparse.ArgumentParser();p.add_argument('--start',default='2023-01-01');p.add_argument('--end',default='2026-11-06');p.add_argument('--output',default='replay_output');a=p.parse_args()
    start=pd.Timestamp(a.start,tz='UTC');end=pd.Timestamp(a.end,tz='UTC')
    if end<=start: p.error('end must be after start')
    out=Path(a.output);out.mkdir(parents=True,exist_ok=True)
    for sym in ('BTCUSDT','ETHUSDT'):
        d=pd.read_csv(DATA_DIR/f'{sym.lower()}_spot_4h.csv',parse_dates=['open_time']).set_index('open_time').sort_index()
        d.index=pd.to_datetime(d.index,utc=True); gaps=validate(d)
        raw=targets(d);prev=raw.loc[raw.index<start]; prior=float(prev.iloc[-1]) if len(prev) else 0.
        window=d.loc[(d.index>=start)&(d.index<end)]
        if window.empty: raise ValueError(f'No candles for {sym} in requested period')
        marks,orders=replay(window,raw.reindex(window.index),prior_target=prior)
        marks.to_csv(out/f'{sym.lower()}_marks.csv');orders.to_csv(out/f'{sym.lower()}_orders.csv',index=False)
        print(f'{sym}: {len(window)} candles, {len(orders)} simulated trades, {len(gaps)} historical gaps, final marked equity {marks.equity.iloc[-1]:.6f}')
if __name__=='__main__':main()
