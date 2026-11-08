"""Fixed 50/50 initial split in independent BTC/ETH accounts; no free rebalancing."""
import json
import numpy as np
import pandas as pd
from iteration_03 import ROOT,OUT,candidates
from audit_backtests import simulate,metrics,bootstrap

winner=json.loads((OUT/'selection.json').read_text())['winner']
rows=[]; paths={}
for cost,lag,case in [(.0015,1,'base'),(.003,1,'cost_x2'),(.0015,2,'delay_4h'),(.003,2,'cost_and_delay')]:
    equities=[]
    for sym in ['BTCUSDT','ETHUSDT']:
        d=pd.read_csv(ROOT/f'{sym.lower()}_spot_4h.csv',parse_dates=['open_time']).set_index('open_time')
        d.index=pd.to_datetime(d.index,utc=True)
        raw=candidates(d)[winner]
        r,_,_=simulate(d,raw,'2023-01-01','2026-11-06',cost,lag)
        rows.append(dict(asset=sym,case=case,**metrics(r)))
        if case=='base':paths[sym]=r
        equities.append((1+r).cumprod())
    equity=pd.concat(equities,axis=1).mean(axis=1)
    r=equity.pct_change();r.iloc[0]=equity.iloc[0]-1
    rows.append(dict(asset='BTC_ETH_initial50_50',case=case,**metrics(r)))
    paths['portfolio_'+case]=r
yearly=[]
for name,r in paths.items():
    if name not in ['BTCUSDT','ETHUSDT','portfolio_base']:continue
    for year,x in r.groupby(r.index.year):
        yearly.append(dict(strategy=name,year=year,return_actual=float((1+x).prod()-1)))
pd.DataFrame(rows).to_csv(OUT/'portfolio_stress.csv',index=False)
pd.DataFrame(yearly).to_csv(OUT/'calendar_returns.csv',index=False)
pd.DataFrame(paths).to_csv(OUT/'portfolio_daily.csv')
print(pd.DataFrame(rows).to_string(index=False));print(pd.DataFrame(yearly).to_string(index=False))

def combine(rs):
    e=pd.concat([(1+r).cumprod() for r in rs],axis=1).mean(axis=1)
    r=e.pct_change();r.iloc[0]=e.iloc[0]-1
    return r

train_s=[];train_b=[];validation_b=[];ds={}
for sym in ['BTCUSDT','ETHUSDT']:
    d=pd.read_csv(ROOT/f'{sym.lower()}_spot_4h.csv',parse_dates=['open_time']).set_index('open_time')
    d.index=pd.to_datetime(d.index,utc=True);ds[sym]=d
    train_s.append(simulate(d,candidates(d)[winner],'2020-01-01','2023-01-01')[0])
    train_b.append(simulate(d,pd.Series(1.,index=d.index),'2020-01-01','2023-01-01')[0])
    validation_b.append(simulate(d,pd.Series(1.,index=d.index),'2023-01-01','2026-11-06')[0])
scale=min(1.,combine(train_s).std()/combine(train_b).std())
reduced=[]
for sym,d in ds.items():
    reduced.append(simulate(d,pd.Series(1.,index=d.index),'2023-01-01','2026-11-06',allocation=scale,rebalance=True)[0])
refs={'passive50_50':combine(validation_b),'risk_reduced_passive':combine(reduced)}
half=[]
for sym,d in ds.items():
    half.append(simulate(d,pd.Series(1.,index=d.index),'2023-01-01','2026-11-06',allocation=.5,rebalance=True)[0])
refs['half_crypto_half_cash']=combine(half)
comparisons=[]
for name,r in refs.items():
    allocation=scale if name.startswith('risk') else (.5 if name=='half_crypto_half_cash' else 1.)
    comparisons.append(dict(reference=name,allocation=allocation,**metrics(r)))
pd.DataFrame(comparisons).to_csv(OUT/'portfolio_benchmarks.csv',index=False)
intervals=[dict(reference=name,**bootstrap(paths['portfolio_base']-r)) for name,r in refs.items()]
pd.DataFrame(intervals).to_csv(OUT/'portfolio_bootstrap.csv',index=False)
print('BENCHMARKS',pd.DataFrame(comparisons).to_string(index=False))
print('DIFFERENCES',pd.DataFrame(intervals).to_string(index=False))
pd.DataFrame({**paths,**refs}).to_csv(OUT/'comparison_daily.csv')
