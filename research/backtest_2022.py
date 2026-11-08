"""Fetch 2021-22 Binance spot candles, then replay the frozen strategy for 2022.

2021 is indicator warm-up; 2022 was previously used during strategy selection.
The fresh download is a data consistency check, not an independent holdout.
"""
from pathlib import Path
import sys, json, hashlib
from datetime import datetime, timezone
import numpy as np
import pandas as pd
import requests

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent))
from quantbot.strategy import targets
from quantbot.data import validate
from quantbot.ledger import replay
from audit_backtests import simulate, metrics

OUT=ROOT/'backtest_2022_results'
API='https://api.binance.com/api/v3/klines'
START=pd.Timestamp('2021-01-01',tz='UTC')
END=pd.Timestamp('2023-01-01',tz='UTC')
TEST=pd.Timestamp('2022-01-01',tz='UTC')
INTERVAL=4*60*60*1000

def download(symbol):
    rows=[]; start=int(START.timestamp()*1000); end=int(END.timestamp()*1000)
    with requests.Session() as s:
        while start<end:
            r=s.get(API,params={'symbol':symbol,'interval':'4h','startTime':start,'endTime':end-1,'limit':1000},timeout=30)
            r.raise_for_status(); part=r.json()
            if not isinstance(part,list) or not part: raise RuntimeError(f'No candles for {symbol} at {start}')
            rows.extend(part); nxt=int(part[-1][0])+INTERVAL
            if nxt<=start: raise RuntimeError('Pagination did not advance')
            start=nxt
    d=pd.DataFrame(rows,columns=['open_ms','open','high','low','close','volume','close_ms','quote_volume','trades','taker_base','taker_quote','ignore'])
    d.index=pd.to_datetime(d.open_ms,unit='ms',utc=True); d.index.name='open_time'
    for k in ['open','high','low','close','volume']: d[k]=pd.to_numeric(d[k],errors='raise')
    d=d[['open','high','low','close','volume']]
    gaps=validate(d)
    expected=pd.date_range(START,END,freq='4h',inclusive='left')
    if not d.index.equals(expected) or len(gaps): raise ValueError(f'Missing, duplicate or unexpected candles for {symbol}')
    return d

def metric(r):
    m=metrics(r)
    return {'total_return':float((1+r).prod()-1),'sharpe_daily_rf0':m['Sharpe'],'max_drawdown_daily':m['MaxDD'],'annual_vol_daily':m['Vol']}

def combine(a,b):
    e=pd.concat([(1+a).cumprod(),(1+b).cumprod()],axis=1).mean(axis=1)
    r=e.pct_change();r.iloc[0]=e.iloc[0]-1
    return r

def main():
    OUT.mkdir(exist_ok=True)
    frames={}; signals={}; old_frames={}; data_checks={}
    for sym in ('BTCUSDT','ETHUSDT'):
        d=download(sym);frames[sym]=d;signals[sym]=targets(d)
        path=OUT/f'{sym.lower()}_spot_4h_2021_2022.csv';d.to_csv(path)
        old=pd.read_csv(ROOT/f'{sym.lower()}_spot_4h.csv',parse_dates=['open_time']).set_index('open_time').sort_index()
        old.index=pd.to_datetime(old.index,utc=True)
        old_frames[sym]=old
        old22=old.loc[(old.index>=TEST)&(old.index<END),['open','high','low','close','volume']]
        new22=d.loc[(d.index>=TEST)&(d.index<END)]
        if not new22.index.equals(old22.index): raise AssertionError(f'Cached timestamps differ for {sym}')
        mismatch=int((~np.isclose(new22.to_numpy(),old22.to_numpy(),rtol=1e-10,atol=1e-10)).sum())
        original_signal=targets(old).reindex(new22.index);new_signal=signals[sym].reindex(new22.index)
        data_checks[sym]={'candles_2021_2022':len(d),'candles_2022':len(new22),'missing':0,'different_ohlcv_values':mismatch,'different_targets':int((original_signal!=new_signal).sum()),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
    rows=[];series={}
    for sym,d in frames.items():
        raw=signals[sym];bh=pd.Series(1.,index=d.index)
        for cost,lag,case in [(.0015,1,'base'),(.003,1,'double_cost'),(.0015,2,'delay_4h'),(.003,2,'double_cost_and_delay')]:
            r,entries,turn=simulate(d,raw,'2022-01-01','2023-01-01',cost=cost,lag=lag)
            rows.append(dict(asset=sym,strategy='frozen',case=case,entries=entries,**metric(r)))
            series[(sym,'frozen',case)]=r
        for name,allocation,rebalance in [('buy_hold',1.,False),('half_crypto_half_cash',.5,True)]:
            r,entries,turn=simulate(d,bh,'2022-01-01','2023-01-01',cost=.0015,allocation=allocation,rebalance=rebalance)
            rows.append(dict(asset=sym,strategy=name,case='base',entries=entries,**metric(r)))
            series[(sym,name,'base')]=r
        w=d.loc[(d.index>=TEST)&(d.index<END)]
        prior=raw.loc[raw.index<TEST].iloc[-1]
        marks,orders=replay(w,raw.reindex(w.index),fee=.0015,prior_target=float(prior))
        marked_after_exit=marks.equity.iloc[-1]-marks.units.iloc[-1]*marks.close.iloc[-1]*.0015
        assert np.isclose(marked_after_exit,(1+series[(sym,'frozen','base')]).prod(),atol=1e-10)
        orders.to_csv(OUT/f'{sym.lower()}_orders.csv',index=False)
        data_checks[sym]['independent_ledger_matches']=True
    for strategy,case in [('frozen','base'),('frozen','double_cost'),('frozen','delay_4h'),('frozen','double_cost_and_delay'),('buy_hold','base'),('half_crypto_half_cash','base')]:
        r=combine(series[('BTCUSDT',strategy,case)],series[('ETHUSDT',strategy,case)])
        rows.append(dict(asset='BTC_ETH_initial50_50',strategy=strategy,case=case,entries=None,**metric(r)))
        series[('portfolio',strategy,case)]=r
    # Set passive exposure from PRE-2022 volatility only; historical warm-up uses cached 2020 data.
    prev_s=[];prev_b=[]
    for sym,old in old_frames.items():
        prev_s.append(simulate(old,targets(old),'2021-01-01','2022-01-01',cost=.0015)[0])
        prev_b.append(simulate(old,pd.Series(1.,index=old.index),'2021-01-01','2022-01-01',cost=.0015)[0])
    scale=float(min(1.,combine(*prev_s).std()/combine(*prev_b).std()))
    scaled=[]
    for sym,d in frames.items():
        scaled.append(simulate(d,pd.Series(1.,index=d.index),'2022-01-01','2023-01-01',cost=.0015,allocation=scale,rebalance=True)[0])
    r=combine(*scaled)
    rows.append(dict(asset='BTC_ETH_initial50_50',strategy='risk_calibrated_in_2021',case='base',entries=None,allocation=scale,**metric(r)))
    series[('portfolio','risk_calibrated_in_2021','base')]=r
    result=pd.DataFrame(rows);result.to_csv(OUT/'results.csv',index=False)
    pd.DataFrame({f'{a}_{s}_{c}':r for (a,s,c),r in series.items()}).to_csv(OUT/'daily_returns.csv')
    monthly=pd.DataFrame({f'{a}_{s}_{c}':r for (a,s,c),r in series.items()}).resample('MS').apply(lambda x:(1+x).prod()-1)
    monthly.to_csv(OUT/'monthly_returns.csv')
    (OUT/'data_checks.json').write_text(json.dumps({'source':API,'downloaded_utc':datetime.now(timezone.utc).isoformat(),'interval':'4h','warmup':'2021-01-01 to 2021-12-31 UTC','backtest':'2022-01-01 to 2022-12-31 UTC','risk_benchmark_crypto_fraction':scale,'risk_benchmark_calibration':'2021 using prior cached data for indicator warm-up','note':'2022 was part of model selection; same exchange is not independent validation','checks':data_checks},indent=2))
    print(result.to_string(index=False));print('DATA CHECKS',json.dumps(data_checks))

if __name__=='__main__':main()
