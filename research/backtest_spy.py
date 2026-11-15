"""Frozen daily approximation of the 4h crypto trend rule, on SPY.

OHLC are adjusted with Yahoo's adjusted-close factor: a total-return proxy,
not executable historical prices or explicit dividend cash accounting.
No strategy parameters are optimized on SPY by this script.
"""
from pathlib import Path
from datetime import datetime, timezone
import hashlib, json, sys
import numpy as np
import pandas as pd
import requests

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent))
from quantbot.ledger import replay

OUT=ROOT/'backtest_spy_results'
URL='https://query1.finance.yahoo.com/v8/finance/chart/SPY'
# Fixed cutoff as requested: market data through Nov 13, 2026.
END=pd.Timestamp('2026-11-14',tz='UTC')

def download():
    r=requests.get(URL,params={'period1':0,'period2':int(END.timestamp()),'interval':'1d','events':'div,splits'},headers={'User-Agent':'Mozilla/5.0'},timeout=30)
    r.raise_for_status(); data=r.json()['chart']['result'][0]
    quote=pd.DataFrame(data['indicators']['quote'][0]);adj=pd.Series(data['indicators']['adjclose'][0]['adjclose'])
    idx=pd.to_datetime(data['timestamp'],unit='s',utc=True).tz_convert('America/New_York').tz_localize(None).normalize()
    quote.index=idx;adj.index=idx
    frame=quote[['open','high','low','close','volume']].copy()
    if frame.isna().any().any() or adj.isna().any():raise ValueError('Missing SPY bars or adjusted prices')
    if frame.index.has_duplicates or not frame.index.is_monotonic_increasing:raise ValueError('Invalid date order')
    factor=adj/frame.close
    for k in ['open','high','low','close']:frame[k]=frame[k]*factor
    frame.index.name='date'
    if (frame[['open','high','low','close']]<=0).any().any():raise ValueError('Nonpositive price')
    if ((frame.low>frame[['open','close']].min(axis=1))|(frame.high<frame[['open','close']].max(axis=1))).any():raise ValueError('Invalid OHLC')
    return frame

def signal(d):
    c=d.close
    # 20/100/200 crypto 4h bars are roughly 3.3/16.7/33 calendar days,
    # approximated as 3/12/24 US trading sessions (5/7 calendar days).
    fast=c.ewm(span=3,adjust=False).mean();slow=c.ewm(span=12,adjust=False).mean()
    trend=(fast>slow)&(c>c.rolling(24).mean())
    # Three 4h bars = 12 hours: one daily confirmation is the nearest daily proxy.
    vol=c.pct_change().rolling(21,min_periods=14).std()*np.sqrt(252)
    size=((.30/vol).clip(0,1)*4).round()/4
    # Freeze weekly size at Friday close. If Friday is closed, retain prior size.
    size=size.where(d.index.weekday==4).ffill().fillna(0.)
    return (trend.astype(float)*size).rename('target')

def simulate(d,raw,start,end,fee=.0015,lag=1,constant_weight=None):
    x=d.loc[(d.index>=pd.Timestamp(start))&(d.index<pd.Timestamp(end))]
    if x.empty:raise ValueError('Empty period')
    wanted=raw.shift(lag).reindex(x.index).fillna(0.).to_numpy()
    cash=1.; units=0.; old=-1.; eq=[];orders=0; exposure=[]
    for i,(op,cl) in enumerate(x[['open','close']].to_numpy()):
        w=float(wanted[i]) if constant_weight is None else constant_weight
        if w!=old or constant_weight==.5: # daily rebalance for the 50/50 benchmark
            before=cash+units*op; desired=w*before/op; delta=desired-units
            delta/=1+w*fee*np.sign(delta)
            cash-=delta*op+abs(delta)*op*fee;units+=delta
            if abs(delta)>1e-12:orders+=1
            if cash < -1e-9 or units < -1e-9:raise ArithmeticError('Negative balance')
            old=w
        equity=cash+units*cl;eq.append(equity);exposure.append(units*cl/equity)
    # Charge hypothetical final sale, keeping cash at zero yield.
    eq[-1]-=units*x.close.iloc[-1]*fee
    daily=pd.Series(eq,index=x.index)
    ret=daily.pct_change();ret.iloc[0]=daily.iloc[0]-1
    return ret,orders,float(np.mean(exposure))

def metrics(r):
    eq=np.r_[1.,(1+r).cumprod().to_numpy()]; sd=r.std(ddof=1)
    years=((r.index[-1]-r.index[0]).days+1)/365.25
    return dict(total_return=float(eq[-1]-1),CAGR=float(eq[-1]**(1/years)-1),Sharpe=float(r.mean()/sd*np.sqrt(252)) if sd else 0.,MaxDD=float((eq/np.maximum.accumulate(eq)-1).min()),vol=float(sd*np.sqrt(252)))

def main():
    OUT.mkdir(exist_ok=True);d=download();path=OUT/'spy_daily_adjusted.csv';d.to_csv(path)
    target=signal(d)
    # Historical prefix invariance against future prices altered after 2010.
    i=d.index.searchsorted(pd.Timestamp('2010-01-01')); changed=d.copy(); changed.iloc[i:,changed.columns.get_indexer(['open','high','low','close'])]*=1.5
    assert np.allclose(target.iloc[:i],signal(changed).iloc[:i])
    rows=[];allreturns={}
    end='2026-11-14'
    periods=[('total','1994-01-01',end),('1994_2009','1994-01-01','2010-01-01'),('2010_2019','2010-01-01','2020-01-01'),('2020_2026','2020-01-01',end),('2008','2008-01-01','2009-01-01'),('2020','2020-01-01','2021-01-01'),('2022','2022-01-01','2023-01-01')]
    for name,raw,weight in [('strategy',target,None),('buy_hold',pd.Series(1.,index=d.index),1.),('half_spy_half_cash',pd.Series(.5,index=d.index),.5)]:
        cases=[('zero_cost',0.,1),('cost_5bp',.0005,1),('base',.0015,1),('double_cost',.003,1),('delay_one_session',.0015,2)] if name=='strategy' else [('base',.0015,1),('cost_5bp',.0005,1)]
        for case,fee,lag in cases:
            for label,a,b in periods:
                r,n,exp=simulate(d,raw,a,b,fee,lag,weight)
                rows.append(dict(strategy=name,case=case,period=label,start=str(r.index[0].date()),end=str(r.index[-1].date()),orders=n,mean_exposure=exp,**metrics(r)))
                if label=='total':allreturns[name+'_'+case]=r
    # Separate implementation parity on full run, including opening signal and final exit.
    x=d.loc[d.index>=pd.Timestamp('1994-01-01')]; prior=target.loc[target.index<x.index[0]].iloc[-1]
    marks,orders=replay(x,target.reindex(x.index),fee=.0015,prior_target=prior)
    after_exit=marks.equity.iloc[-1]-marks.units.iloc[-1]*marks.close.iloc[-1]*.0015
    assert np.isclose(after_exit,(1+allreturns['strategy_base']).prod(),atol=1e-9)
    orders.to_csv(OUT/'orders.csv',index=False)
    pd.DataFrame(rows).to_csv(OUT/'results.csv',index=False)
    pd.DataFrame(allreturns).to_csv(OUT/'daily_returns.csv')
    annual=pd.DataFrame({name:ret.groupby(ret.index.year).apply(lambda q:(1+q).prod()-1) for name,ret in allreturns.items()})
    annual.to_csv(OUT/'annual_returns.csv')
    (OUT/'metadata.json').write_text(json.dumps(dict(source=URL,downloaded_utc=datetime.now(timezone.utc).isoformat(),first=str(d.index[0].date()),last=str(d.index[-1].date()),rows=len(d),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),adjustment='OHLC scaled by Yahoo adjusted_close / close: proxy for reinvested dividends; not historical executable prices',calendar='US sessions; holidays not filled; Fridays only for sizing',target='EMA3 > EMA12 and close > SMA24; weekly 30% volatility target over 21 trading sessions rounded to 25%; one session confirmation',fee_per_side=.0015,initial_investment='fresh cash at each period start',cash_yield=0,ledger_parity=True),indent=2))
    print(pd.DataFrame(rows).to_string(index=False));print('DATA',len(d),d.index[0],d.index[-1])

if __name__=='__main__':main()
