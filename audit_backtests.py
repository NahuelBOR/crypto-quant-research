"""Independent audit; no strategy search. Uses cached spot OHLCV, cash and actual units.
Run: python audit_backtests.py. Results are exploratory, not a fresh holdout.
"""
from pathlib import Path
import ast, json, hashlib
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parent

def signal(d,name):
    c=d.close
    if name=='passive': return pd.Series(1.,index=d.index)
    if name=='EMA4h':
        return ((c.ewm(span=20,adjust=False).mean()>c.ewm(span=100,adjust=False).mean()) & (c>c.rolling(200).mean())).astype(float)
    if name=='vote_daily':
        # Daily vote available only after all six bars of that UTC day have closed.
        daily=c.resample('1D').last()
        s=(sum((daily.pct_change(n)>0).astype(int) for n in [30,90,180])>=2).astype(float)
        s.index=s.index+pd.Timedelta(hours=20)
        return s.reindex(d.index).ffill().fillna(0.)
    if name=='ETH_crash':
        vz=(d.volume-d.volume.rolling(30).mean())/d.volume.rolling(30).std()
        trigger=(c.pct_change(6)<-.08)&(vz>1.5)
        # A new trigger extends the holding period, matching the earlier rule.
        return trigger.rolling(2,min_periods=1).max().astype(float)
    raise ValueError(name)

def simulate(d,raw,start,end,cost=.0015,lag=1,allocation=1.,rebalance=False):
    x=d.loc[(d.index>=pd.Timestamp(start,tz='UTC')) & (d.index<pd.Timestamp(end,tz='UTC'))]
    wanted=raw.shift(lag).reindex(x.index).fillna(0.).to_numpy()
    cash=1.; qty=0.; old=-1.; eq=[]; entries=0; turnover=0.
    for i,(op,cl) in enumerate(x[['open','close']].to_numpy()):
        w=float(wanted[i])*allocation
        if w!=old or (rebalance and x.index[i].hour==0):
            wealth=cash+qty*op
            # Exact fee-aware target stock fraction after costs; no borrowing.
            target_before=w*wealth/op
            delta=(target_before-qty)/(1+w*cost*np.sign(target_before-qty))
            if delta>1e-12 and qty<1e-12: entries+=1
            cash-=delta*op+abs(delta)*op*cost
            qty+=delta; turnover+=abs(delta)*op
            assert cash>=-1e-9 and qty>=-1e-9
            old=w
        eq.append(cash+qty*cl)
    # Liquidate at the final known close; charge the exit as well.
    eq[-1]-=qty*x.close.iloc[-1]*cost
    e=pd.Series(eq,index=x.index).resample('1D').last()
    r=e.pct_change(); r.iloc[0]=e.iloc[0]-1
    return r,entries,turnover

def metrics(r):
    e=np.r_[1.,(1+r).cumprod().to_numpy()]
    sd=r.std(ddof=1)
    return dict(CAGR=float(e[-1]**(365.25/len(r))-1),Sharpe=float(r.mean()/sd*np.sqrt(365.25)) if sd else 0.,MaxDD=float((e/np.maximum.accumulate(e)-1).min()),Vol=float(sd*np.sqrt(365.25)))

def bootstrap(x,block=30,B=2000):
    a=x.to_numpy(); n=len(a); rng=np.random.default_rng(111)
    vals=[]
    for _ in range(B):
        starts=rng.integers(0,n,size=int(np.ceil(n/block)))
        ix=(starts[:,None]+np.arange(block)[None,:]).ravel()[:n]%n
        vals.append(a[ix].mean()*365.25)
    return dict(mean_ann=float(a.mean()*365.25),lo95=float(np.quantile(vals,.025)),hi95=float(np.quantile(vals,.975)))

def checks():
    # A flat asset must lose exactly entry/exit costs; a passive account must track units.
    ix=pd.date_range('2020-01-01',periods=12,freq='4h',tz='UTC')
    d=pd.DataFrame({'open':100.,'close':100.},index=ix)
    r,_,_=simulate(d,pd.Series(1.,index=ix),'2020-01-01','2020-01-03',.01,lag=0)
    assert np.isclose((1+r).prod(),.99/1.01)
    d['close']=np.arange(100.,112.); d['open']=d.close
    r,_,_=simulate(d,pd.Series(1.,index=ix),'2020-01-01','2020-01-03',0.,lag=0)
    assert np.isclose((1+r).prod(),1.11)
    # Reproduce the legacy weekly-hold bug with the original function, without running its main.
    tree=ast.parse((ROOT/'ensemble_quant_backtest.py').read_text())
    node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='cross_target')
    dates=pd.date_range('2020-01-01',periods=100,freq='D',tz='UTC')
    px=pd.DataFrame({str(i):np.exp(np.arange(100)*(.001+i*.001)) for i in range(4)},index=dates)
    noise=pd.DataFrame(np.random.default_rng(0).normal(0,.01,(100,4)),index=dates,columns=px.columns)
    scope=dict(pd=pd,np=np,px=px,spotret=noise,days=dates,SYMS=list(px.columns))
    exec(compile(ast.Module(body=[node],type_ignores=[]),'legacy','exec'),scope)
    w=scope['cross_target'](30,1)
    assert (w.loc[w.index.weekday!=0].abs().sum(axis=1)==0).all()
    assert w.abs().sum().sum()>0
    return ['flat-price fee identity PASS','passive units identity PASS','legacy weekly positions zero outside Monday CONFIRMED']

if __name__=='__main__':
    checklog=checks(); frames={}; data=[]
    for sym in ['BTCUSDT','ETHUSDT']:
        path=ROOT/f'{sym.lower()}_spot_4h.csv'
        d=pd.read_csv(path,parse_dates=['open_time']).set_index('open_time').sort_index()
        d.index=pd.to_datetime(d.index,utc=True)
        counts=d.groupby(d.index.floor('D')).size(); last=counts[counts==6].index[-1]
        d=d.loc[d.index<last+pd.Timedelta(days=1)]
        bad=((d.low>d[['open','close']].min(axis=1))|(d.high<d[['open','close']].max(axis=1))|(d.low>d.high)|(d.close<=0)).sum()
        assert bad==0 and not d.index.duplicated().any()
        data.append(dict(symbol=sym,rows=len(d),gaps=int((d.index.to_series().diff().dropna()!=pd.Timedelta(hours=4)).sum()),bad_ohlc=int(bad),end=str(d.index[-1]),sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
        frames[sym]=d
    end=(min(x.index[-1].floor('D') for x in frames.values())+pd.Timedelta(days=1)).strftime('%Y-%m-%d')
    results=[]; boots=[]; series={}
    for sym,name in [('BTCUSDT','EMA4h'),('BTCUSDT','vote_daily'),('ETHUSDT','ETH_crash')]:
        d=frames[sym]; raw=signal(d,name); bh=signal(d,'passive')
        # Prefix stability: future price edits must not alter earlier signals.
        cut=len(d)//2; altered=d.copy(); altered.iloc[cut:,altered.columns.get_loc('close')]*=1.7
        assert np.allclose(signal(altered,name).iloc[:cut],raw.iloc[:cut])
        checklog.append(name+' future-perturbation PASS')
        tr,_,_=simulate(d,raw,'2020-01-01','2023-01-01')
        tb,_,_=simulate(d,bh,'2020-01-01','2023-01-01')
        scale=min(1.,tr.std()/tb.std())
        for fee,lag,label in [(.0015,1,'base'),(.003,1,'cost_x2'),(.0015,2,'delay_4h')]:
            for period,a,b in [('train','2020-01-01','2023-01-01'),('historical_validation','2023-01-01',end),('2026','2026-01-01',end)]:
                r,entries,turn=simulate(d,raw,a,b,fee,lag)
                results.append(dict(asset=sym,strategy=name,case=label,period=period,entries=entries,**metrics(r)))
                if period=='historical_validation' and label=='base':
                    passive,_,_=simulate(d,bh,a,b,fee,1)
                    matched,_,_=simulate(d,bh,a,b,fee,1,scale,True)
                    for tag,v in [('passive',passive),('risk_matched_passive',matched)]:
                        results.append(dict(asset=sym,strategy=name+'_'+tag,case=label,period=period,allocation=scale if tag.startswith('risk') else 1.,**metrics(v)))
                    boots.append(dict(strategy=name,comparison='absolute_mean_zero_cash',**bootstrap(r)))
                    boots.append(dict(strategy=name,comparison='minus_risk_matched',**bootstrap(r-matched)))
                    series[name]=r
                    series[name+'_matched']=matched
    pd.DataFrame(results).to_csv(ROOT/'audit_results.csv',index=False)
    pd.DataFrame(boots).to_csv(ROOT/'audit_bootstrap.csv',index=False)
    pd.DataFrame(series).to_csv(ROOT/'audit_daily_returns.csv')
    (ROOT/'audit_checks.json').write_text(json.dumps(dict(checks=checklog,data=data,end_exclusive=end),indent=2))
    print(pd.DataFrame(results).to_string(index=False))
    print(pd.DataFrame(boots).to_string(index=False))
    print(checklog,data)
