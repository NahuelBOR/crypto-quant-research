"""Retrospective test of the frozen strategy on Binance spot 2018-2019.

The candidate was designed with later data. Earlier daily history was inspected
in previous research, so this is an additional historical test, not blind proof.
"""
from pathlib import Path
from datetime import datetime, timezone
import hashlib, json, sys
import numpy as np
import pandas as pd
import requests

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent))
from quantbot.strategy import targets
from quantbot.data import validate
from quantbot.ledger import replay
from audit_backtests import simulate, metrics, bootstrap
from backtest_2022 import combine

OUT=ROOT/'backtest_2018_2019_results'
API='https://api.binance.com/api/v3/klines'
START=pd.Timestamp('2017-08-17 04:00:00',tz='UTC')
TEST=pd.Timestamp('2018-01-01',tz='UTC')
END=pd.Timestamp('2020-01-01',tz='UTC')
INTERVAL=4*60*60*1000

def download(symbol):
    rows=[]; start=int(START.timestamp()*1000);end=int(END.timestamp()*1000)
    with requests.Session() as session:
        while start<end:
            response=session.get(API,params={'symbol':symbol,'interval':'4h','startTime':start,'endTime':end-1,'limit':1000},timeout=30)
            response.raise_for_status();batch=response.json()
            if not isinstance(batch,list) or not batch: raise RuntimeError(f'No candles for {symbol}: {start}')
            rows.extend(batch); next_start=int(batch[-1][0])+INTERVAL
            if next_start<=start: raise RuntimeError('Pagination did not advance')
            start=next_start
    d=pd.DataFrame(rows,columns=['open_ms','open','high','low','close','volume','close_ms','quote_volume','trades','taker_base','taker_quote','ignore'])
    d.index=pd.to_datetime(d.open_ms,unit='ms',utc=True);d.index.name='open_time'
    for col in ['open','high','low','close','volume']:d[col]=pd.to_numeric(d[col],errors='raise')
    d=d[['open','high','low','close','volume']]
    validate(d)
    if d.index[0]!=START or d.index[-1]!=END-pd.Timedelta(hours=4): raise ValueError(f'Missing endpoints for {symbol}')
    return d

def main():
    OUT.mkdir(exist_ok=True); frames={}; signal={}; checks={}; rows=[]; series={}
    for sym in ('BTCUSDT','ETHUSDT'):
        d=download(sym);frames[sym]=d;signal[sym]=targets(d)
        path=OUT/f'{sym.lower()}_spot_4h_2017_2019.csv';d.to_csv(path)
        expected=pd.date_range(START,END,freq='4h',inclusive='left')
        missing=expected.difference(d.index)
        days=d.loc[(d.index>=TEST)&(d.index<END)].groupby(d.index[(d.index>=TEST)&(d.index<END)].floor('D')).size()
        expected_days=pd.date_range(TEST,END,freq='D',inclusive='left')
        if not days.index.equals(expected_days):raise ValueError(f'At least one whole day missing for {sym}')
        # Verify signals do not depend on changing prices after a cutoff.
        cut=d.index.searchsorted(pd.Timestamp('2019-01-01',tz='UTC'))
        altered=d.copy();altered.iloc[cut:,altered.columns.get_indexer(['open','high','low','close'])]*=1.5
        assert np.allclose(signal[sym].iloc[:cut],targets(altered).iloc[:cut])
        prior=signal[sym].loc[signal[sym].index<TEST].iloc[-1]
        x=d.loc[(d.index>=TEST)&(d.index<END)]
        marks,orders=replay(x,signal[sym].reindex(x.index),fee=.0015,prior_target=float(prior))
        series[(sym,'frozen','base')],entries,_=simulate(d,signal[sym],'2018-01-01','2020-01-01',cost=.0015)
        after_exit=marks.equity.iloc[-1]-marks.units.iloc[-1]*marks.close.iloc[-1]*.0015
        assert np.isclose(after_exit,(1+series[(sym,'frozen','base')]).prod(),atol=1e-10)
        orders.to_csv(OUT/f'{sym.lower()}_orders.csv',index=False)
        checks[sym]={'candles':len(d),'test_candles':len(x),'missing_count':len(missing),'missing_utc':[str(t) for t in missing], 'test_days_with_gaps':int((days<6).sum()),'ledger_parity':True,'no_future_signal_change':True,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
        for fee,lag,case in [(.0015,1,'base'),(.003,1,'double_cost'),(.0015,2,'delay_4h'),(.003,2,'double_cost_and_delay')]:
            r,_,_=simulate(d,signal[sym],'2018-01-01','2020-01-01',cost=fee,lag=lag)
            series[(sym,'frozen',case)]=r
        # 25% exposure is a diagnostic added after inspecting the initial results,
        # chosen to approximate the observed risk; it is not a pre-registered benchmark.
        for name,weight,rebalance in [('buy_hold',1.,False),('half_crypto_half_cash',.5,True),('quarter_crypto_three_quarters_cash',.25,True)]:
            r,_,_=simulate(d,pd.Series(1.,index=d.index),'2018-01-01','2020-01-01',cost=.0015,allocation=weight,rebalance=rebalance)
            series[(sym,name,'base')]=r
    for strategy,case in [('frozen','base'),('frozen','double_cost'),('frozen','delay_4h'),('frozen','double_cost_and_delay'),('buy_hold','base'),('half_crypto_half_cash','base'),('quarter_crypto_three_quarters_cash','base')]:
        series[('portfolio',strategy,case)]=combine(series[('BTCUSDT',strategy,case)],series[('ETHUSDT',strategy,case)])
    for (asset,strategy,case),r in series.items():
        for period,x in [('2018_2019',r),('2018',r.loc[r.index.year==2018]),('2019',r.loc[r.index.year==2019])]:
            m=metrics(x); rows.append(dict(asset=asset,strategy=strategy,case=case,period=period,total_return=float((1+x).prod()-1),**m))
    result=pd.DataFrame(rows);result.to_csv(OUT/'results.csv',index=False)
    pd.DataFrame({f'{a}_{s}_{c}':r for (a,s,c),r in series.items()}).to_csv(OUT/'daily_returns.csv')
    difference=series[('portfolio','frozen','base')]-series[('portfolio','quarter_crypto_three_quarters_cash','base')]
    pd.DataFrame([{'comparison':'frozen_minus_25pct_crypto',**bootstrap(difference)}]).to_csv(OUT/'bootstrap.csv',index=False)
    (OUT/'data_checks.json').write_text(json.dumps({'source':API,'downloaded_utc':datetime.now(timezone.utc).isoformat(),'interval':'4h','warmup':'2017-08-17 to 2017-12-31 UTC','test':'2018-01-01 to 2019-12-31 UTC','note':'Frozen rule selected using later years; prior research inspected 2018-2019 daily data. Gaps are not filled: rolling indicators count available bars and execution moves to the next available open. 25% passive benchmark chosen after inspecting the initial results.','checks':checks},indent=2))
    print('PORTFOLIO',result[(result.asset=='portfolio')].to_string(index=False))
    print('INDIVIDUAL',result[(result.asset!='portfolio')&(result.strategy=='frozen')&(result['case']=='base')].to_string(index=False))
    print('DATA',json.dumps(checks))

if __name__=='__main__':main()
