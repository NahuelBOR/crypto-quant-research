"""BTC/ETH pair-trading screen, using lagged signals and executable next-bar opens."""
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parent
PERIODS=[('train','2020-01-01','2023-01-01'),('test_2023_26','2023-01-01',None),
         ('2023','2023-01-01','2024-01-01'),('2024_25','2024-01-01','2026-01-01'),('2026_ytd','2026-01-01',None)]

def load(sym):
    d=pd.read_csv(ROOT/f'{sym.lower()}_fut_4h.csv',parse_dates=['open_time']).set_index('open_time').sort_index()
    d.index=pd.to_datetime(d.index,utc=True)
    return d

def adf_resid_tstat(resid,maxlag=12):
    """ADF t-stat with AIC-selected lag count; Engle-Granger critical values are only approximate."""
    x=np.asarray(resid,float); dx=np.diff(x); level=x[:-1]
    best=None
    for p in range(maxlag+1):
        n=len(dx)-p
        if n<100: continue
        cols=[np.ones(n),level[p:]]+[dx[p-j-1:len(dx)-j-1] for j in range(p)]
        X=np.column_stack(cols); y=dx[p:]
        b=np.linalg.lstsq(X,y,rcond=None)[0]; err=y-X@b
        sse=max(float(err@err),1e-30); k=X.shape[1]
        aic=n*np.log(sse/n)+2*k
        if best is None or aic<best[0]:
            cov=(sse/(n-k))*np.linalg.inv(X.T@X)
            t=b[1]/np.sqrt(cov[1,1])
            best=(aic,p,float(t))
    return best

def regression_params(lb,le,window=None):
    if window is None:
        a=lb.loc[:'2022-12-31 20:00:00+00:00'].mean()
        b=le.loc[:'2022-12-31 20:00:00+00:00'].mean()
        cov=lb.loc[:'2022-12-31 20:00:00+00:00'].cov(le.loc[:'2022-12-31 20:00:00+00:00'])
        var=le.loc[:'2022-12-31 20:00:00+00:00'].var()
        beta=cov/var
        return pd.Series(beta,index=lb.index),pd.Series(a-beta*b,index=lb.index)
    beta=lb.rolling(window,min_periods=window).cov(le).shift(1)/le.rolling(window,min_periods=window).var().shift(1)
    alpha=lb.rolling(window,min_periods=window).mean().shift(1)-beta*le.rolling(window,min_periods=window).mean().shift(1)
    return beta,alpha

def make_weights(lb,le,window,entry,exit_z,mode):
    if mode=='static': beta,alpha=regression_params(lb,le)
    else: beta,alpha=regression_params(lb,le,window)
    spread=lb-alpha-beta*le
    mu=spread.rolling(window,min_periods=window).mean().shift(1)
    sd=spread.rolling(window,min_periods=window).std(ddof=1).shift(1)
    z=(spread-mu)/sd.replace(0,np.nan)
    side=0; side_arr=np.zeros(len(lb)); beta_arr=beta.to_numpy(float); zz=z.to_numpy(float)
    for i in range(len(lb)):
        zi=zz[i]; bi=beta_arr[i]
        if not np.isfinite(zi) or not np.isfinite(bi) or bi<=0:
            side=0
        else:
            if side==0:
                if zi<=-entry: side=1
                elif zi>=entry: side=-1
            elif abs(zi)<=exit_z or abs(zi)>=4.0:
                side=0
        side_arr[i]=side
    # Store the beta at signal time only when the position changes; weights are applied at next open.
    btc=np.zeros(len(lb)); eth=np.zeros(len(lb)); active_beta=1.
    prev=0
    for i,s in enumerate(side_arr):
        if s!=prev:
            if s: active_beta=beta_arr[i]
            prev=s
        if s:
            gross=1+abs(active_beta)
            btc[i]=s/gross
            eth[i]=-s*active_beta/gross
    return pd.DataFrame({'btc':btc,'eth':eth},index=lb.index),z,beta

def returns(weights,btc,eth,funding_btc,funding_eth,fee_bps=5):
    # A signal measured at candle close is first executable at the following candle open.
    weights=weights.shift(1).fillna(0.)
    idx=weights.index; wb=weights.btc.to_numpy(float); we=weights.eth.to_numpy(float)
    oo_b=btc.open.to_numpy(float); cc_b=btc.close.to_numpy(float); oo_e=eth.open.to_numpy(float); cc_e=eth.close.to_numpy(float)
    fb=funding_btc.reindex(idx).fillna(0).to_numpy(float); fe=funding_eth.reindex(idx).fillna(0).to_numpy(float)
    r=np.zeros(len(idx)); fee=fee_bps/1e4
    prev_b=prev_e=None; oldb=olde=0.
    for i in range(len(idx)):
        gap=0.
        if prev_b is not None:
            gap=oldb*(oo_b[i]/prev_b-1)+olde*(oo_e[i]/prev_e-1)
        turn=abs(wb[i]-oldb)+abs(we[i]-olde)
        intraday=wb[i]*(cc_b[i]/oo_b[i]-1)+we[i]*(cc_e[i]/oo_e[i]-1)
        fcost=wb[i]*fb[i]+we[i]*fe[i]
        r[i]=gap+intraday-fee*turn-fcost
        prev_b,prev_e=cc_b[i],cc_e[i]
        oldb,olde=wb[i],we[i]
    return pd.Series(r,index=idx)

def stats(r):
    e=(1+r).cumprod(); n=len(r); years=n/(6*365.25)
    sharpe=r.mean()/r.std(ddof=1)*np.sqrt(6*365.25) if r.std(ddof=1)>0 else np.nan
    cagr=e.iloc[-1]**(1/years)-1 if years>0 and e.iloc[-1]>0 else -1
    return cagr,sharpe,(e/e.cummax()-1).min(),e.iloc[-1]-1

def period_returns(r,label,start,end):
    mask=r.index>=pd.Timestamp(start,tz='UTC')
    if end: mask &= r.index<pd.Timestamp(end,tz='UTC')
    return r.loc[mask]

btc=load('BTCUSDT'); eth=load('ETHUSDT')
idx=btc.index.intersection(eth.index); btc=btc.loc[idx]; eth=eth.loc[idx]
lb=np.log(btc.close); le=np.log(eth.close)

# Historical funding is aligned to the nearest futures candle; event rate is charged on held notional.
funds={}
for sym in ('BTCUSDT','ETHUSDT'):
    c=pd.read_csv(ROOT/f'{sym.lower()}_carry_4h.csv',index_col=0,parse_dates=True); c.index=pd.to_datetime(c.index,utc=True)
    s=c.funding.dropna(); out=pd.Series(0.,index=idx)
    for t,v in s.items():
        j=idx.get_indexer([t],method='nearest')[0]
        if abs((idx[j]-t).total_seconds())<=2*3600: out.iloc[j]+=float(v)
    funds[sym]=out

train_mask=idx<pd.Timestamp('2023-01-01',tz='UTC')
tr=lb[train_mask].dropna().index
static_beta=lb.loc[tr].cov(le.loc[tr])/le.loc[tr].var()
static_alpha=lb.loc[tr].mean()-static_beta*le.loc[tr].mean()
train_resid=(lb.loc[tr]-static_alpha-static_beta*le.loc[tr]).dropna()
adf=adf_resid_tstat(train_resid)
print(f'TRAIN Engle-Granger residual diagnostic: beta={static_beta:.5f}, ADF t={adf[2]:.3f}, AIC lags={adf[1]} (approx 5% Engle-Granger critical value for 2 series+constant ~ -3.34)')

results=[]; configs=[]
for mode in ('static','rolling'):
  for days in (30,90,180):
    w=days*6
    for entry in (1.5,2.0,2.5):
      weights,z,beta=make_weights(lb,le,w,entry,.5,mode)
      for fee in (5,10):
        r=returns(weights,btc,eth,funds['BTCUSDT'],funds['ETHUSDT'],fee)
        ntrades=int((weights.btc.diff().abs()+weights.eth.diff().abs()).gt(0).sum()/2)
        configs.append((mode,days,entry,fee,r,ntrades))
        for label,start,end in PERIODS:
          x=period_returns(r,label,start,end)
          cg,sh,dd,total=stats(x)
          results.append(dict(mode=mode,window_days=days,entry_z=entry,exit_z=.5,fee_bps_per_leg=fee,period=label,CAGR=cg,Sharpe=sh,MaxDD=dd,total_return=total,approx_round_trips=ntrades))

out=pd.DataFrame(results); out.to_csv(ROOT/'btc_eth_stat_arb_summary.csv',index=False)
# Equal-risk passive benchmarks (spot, 50/50 with no leverage), no trades during pair warming excluded via full sample.
retb=btc.close.pct_change().fillna(0); rete=eth.close.pct_change().fillna(0)
bench={'BTC_buy_hold':retb,'BTC_ETH_50_50':.5*retb+.5*rete}
for name,rr in bench.items():
    for label,start,end in PERIODS:
        x=period_returns(rr,label,start,end); cg,sh,dd,total=stats(x)
        results.append(dict(mode=name,window_days=np.nan,entry_z=np.nan,exit_z=np.nan,fee_bps_per_leg=0,period=label,CAGR=cg,Sharpe=sh,MaxDD=dd,total_return=total,approx_round_trips=0))
pd.DataFrame(results).to_csv(ROOT/'btc_eth_stat_arb_summary.csv',index=False)

tab=pd.DataFrame(results)
print('\nTop configurations ranked by training Sharpe, with held-out metrics (5bp/leg):')
trn=tab[(tab.period=='train')&(tab.fee_bps_per_leg==5)&tab['mode'].isin(['static','rolling'])].sort_values('Sharpe',ascending=False).head(8)
for _,row in trn.iterrows():
    print(row[['mode','window_days','entry_z','CAGR','Sharpe','MaxDD','approx_round_trips']].to_dict())
    print(tab[(tab['mode']==row['mode'])&(tab.window_days==row.window_days)&(tab.entry_z==row.entry_z)&(tab.fee_bps_per_leg==5)&(tab.period.isin(['test_2023_26','2023','2024_25','2026_ytd']))][['period','CAGR','Sharpe','MaxDD','total_return']].to_string(index=False))
print('\nBest OOS configurations (diagnostic only; validation already inspected):')
print(tab[(tab.period=='test_2023_26')&(tab.fee_bps_per_leg==5)&tab['mode'].isin(['static','rolling'])].sort_values('Sharpe',ascending=False).head(10)[['mode','window_days','entry_z','CAGR','Sharpe','MaxDD','total_return','approx_round_trips']].to_string(index=False))
print('\nBenchmarks:')
print(tab[(tab['mode'].isin(bench))][['mode','period','CAGR','Sharpe','MaxDD','total_return']].to_string(index=False))
