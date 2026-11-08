import numpy as np, pandas as pd
from pathlib import Path
ROOT=Path(__file__).resolve().parent
FEE_FUT=.0005; FEE_SPOT=.001; MMR=.005
PERIODS=[('train','2020-01-01','2023-01-01'),('test_2023_26','2023-01-01',None),('2023','2023-01-01','2024-01-01'),('2024_25','2024-01-01','2026-01-01'),('2026_ytd','2026-01-01',None)]

def state_machine(index, long_entry, long_exit, short_entry=None, short_exit=None):
    le=long_entry.fillna(False).to_numpy(); lx=long_exit.fillna(False).to_numpy()
    se=(short_entry if short_entry is not None else pd.Series(False,index=index)).fillna(False).to_numpy()
    sx=(short_exit if short_exit is not None else pd.Series(False,index=index)).fillna(False).to_numpy()
    out=np.zeros(len(index)); p=0
    for i in range(len(index)):
        if p==1 and lx[i]: p=0
        elif p==-1 and sx[i]: p=0
        if p==0:
            if le[i]: p=1
            elif se[i]: p=-1
        out[i]=p
    return pd.Series(out,index=index)

def pulse_hold(index, pulse, duration, side):
    out=np.zeros(len(index)); left=0; p=0; a=pulse.fillna(False).to_numpy()
    for i in range(len(index)):
        if a[i]: left=duration; p=side[i] if np.ndim(side) else side
        if left>0: out[i]=p; left-=1
        else: p=0
    return pd.Series(out,index=index)

def make_4h(df, funding):
    c,h,l,o,v=df.close,df.high,df.low,df.open,df.volume; idx=df.index
    ret=c.pct_change(); sig={}
    e20=c.ewm(span=20,adjust=False).mean(); e100=c.ewm(span=100,adjust=False).mean()
    trend=np.sign(e20-e100)
    sig['EMA20_100_LS']=trend.astype(float)
    sig['EMA20_100_LC']=((e20>e100)&(c>c.rolling(200).mean())).astype(float)
    # Donchian 20-bar breakout, exit through 10-bar opposite boundary.
    sig['Donchian20_10_LS']=state_machine(idx,h>h.rolling(20).max().shift(1),l<l.rolling(10).min().shift(1),l<l.rolling(20).min().shift(1),h>h.rolling(10).max().shift(1))
    r2=ret
    sig['OneBar_Reversal_LS']=(-np.sign(r2)).fillna(0)
    mom6=c.pct_change(6)
    sig['Mom24h_LS']=np.sign(mom6).fillna(0)
    rsi_delta=c.diff(); ag=rsi_delta.clip(lower=0).ewm(alpha=.5,adjust=False,min_periods=2).mean(); al=(-rsi_delta.clip(upper=0)).ewm(alpha=.5,adjust=False,min_periods=2).mean(); rsi2=100-100/(1+ag/al.replace(0,np.nan))
    sig['RSI2_Fade_LS']=state_machine(idx,rsi2<10,rsi2>50,rsi2>90,rsi2<50)
    ma=c.rolling(20).mean(); sd=c.rolling(20).std(ddof=0); upper=ma+2*sd; lower=ma-2*sd
    sig['Bollinger20_Fade_LS']=state_machine(idx,c<lower,c>=ma,c>upper,c<=ma)
    vz=(v-v.rolling(30).mean())/v.rolling(30).std(ddof=1)
    sig['VolumeSpike_Reversal']=(-np.sign(ret)).where(vz>2,0).fillna(0)
    # 24h crash continuation short; a single trigger holds for six 4h bars.
    crash=(mom6<-.05)
    sig['CrashShort_24h'] = pulse_hold(idx,crash,6,-1)
    # Violent 24h sell-off plus abnormal volume, fading the move for 8h.
    sig['CrashFade_24h'] = pulse_hold(idx,(mom6<-.08)&(vz>1.5),2,1)
    rv6=ret.rolling(6).std(); rv48=ret.rolling(48).std();
    sig['VolExpansion_Mom']=np.sign(ret).where(rv6>2*rv48,0).fillna(0)
    # Low Bollinger-width regime followed by a 20-bar price breakout.
    width=(upper-lower)/ma; q20=width.rolling(540,min_periods=120).quantile(.2); squeeze=width<q20
    brk=(c>h.rolling(20).max().shift(1)); breakdown=(c<l.rolling(20).min().shift(1))
    sig['Squeeze_Breakout_LS']=state_machine(idx,squeeze&brk,c<ma,squeeze&breakdown,c>ma)
    # Volume-weighted mean reversion.
    vwap=(c*v).rolling(20).sum()/v.rolling(20).sum(); dev=(c-vwap)/c.rolling(20).std(ddof=0)
    sig['VWAP20_Fade_LS']=state_machine(idx,dev<-2,dev>=0,dev>2,dev<=0)
    # News/forum idea: 3-day BTC drop below -5% used as a long-risk gate; apply it to trend longs.
    # A short is taken only when 3-day loss is extreme and market is below the 200-bar trend.
    ma200=c.rolling(200).mean(); ret18=c.pct_change(18)
    sig['CrashGate_Trend']=((e20>e100)&(ret18>-.05)).astype(float)
    sig['CrashShort_TrendGate']=((-1*((ret18<-.05)&(c<ma200))).astype(float))
    # Amihud-like liquidity shock proxy; flat when |return|/dollar-volume exceeds its rolling 95th percentile.
    amihud=ret.abs()/(c*v).replace(0,np.nan); aq=amihud.rolling(540,min_periods=120).quantile(.95)
    sig['LiquidityShock_GatedTrend']=trend.where(amihud<aq,0)
    # Funding event is known after settlement; only update the crowding signal on event bars.
    f=funding.reindex(idx); event=f.notna(); fe=f.loc[event]; f_ma_event=fe.rolling(3,min_periods=3).mean()
    event_signal=pd.Series(np.nan,index=idx); event_signal.loc[event]=(-np.sign(fe)*(fe.abs()>=.0005)).astype(float)
    sig['FundingExtreme_Fade']=event_signal.ffill().fillna(0)
    event_signal2=pd.Series(np.nan,index=idx); event_signal2.loc[event]=(-np.sign(f_ma_event)*(f_ma_event.abs()>=.0003)).fillna(0)
    sig['Funding3_Fade']=event_signal2.ffill().fillna(0)
    # Volatility-managed trend, exposure capped at 1x before external leverage tests.
    rv90=(ret.rolling(6*90).std().shift(1)*np.sqrt(6*365))
    sig['VolTargetTrend40']=trend*np.minimum(1,.40/rv90).replace([np.inf,-np.inf],np.nan).fillna(0)
    return {k:pd.Series(x,index=idx).replace([np.inf,-np.inf],np.nan).fillna(0).astype(float) for k,x in sig.items()},f

def simulate(df, target_raw, funding, leverage=1., fee=FEE_FUT, spot=None, carry=False):
    # Signals use the prior bar close. The account starts with fresh equity for each period.
    desired=target_raw.shift(1).reindex(df.index).fillna(0).to_numpy(dtype=float)
    fund=funding.reindex(df.index).fillna(0).to_numpy(dtype=float)
    if carry:
        s=spot.reindex(df.index)
        sr=s.close.pct_change(fill_method=None).fillna(0).to_numpy(dtype=float)
        pr=df.close.pct_change(fill_method=None).fillna(0).to_numpy(dtype=float)
        if len(sr): sr[0]=s.close.iloc[0]/s.open.iloc[0]-1
        if len(pr): pr[0]=df.close.iloc[0]/df.open.iloc[0]-1
        turn=np.abs(np.diff(np.r_[0.,desired]))
        pnl=(desired*(sr-pr+fund)-turn*(FEE_SPOT+FEE_FUT))/2
        eq=np.cumprod(1+pnl)
        return pnl,eq,False,None,desired

    opens=df.open.to_numpy(dtype=float); highs=df.high.to_numpy(dtype=float); lows=df.low.to_numpy(dtype=float); closes=df.close.to_numpy(dtype=float)
    eq=np.ones(len(df)); pnl=np.zeros(len(df)); alive=True; liquidated=False; liq_i=None
    cash=1.0; qty=0.0; old_signal=0.0; prev_close=None
    liq_fee=.002
    for i in range(len(df)):
        op,hi,lo,cl=opens[i],highs[i],lows[i],closes[i]
        # Mark any position through the close-to-next-open move before adjusting it.
        cash_open=cash + (qty*(op-prev_close) if prev_close is not None and alive else 0.0)
        sig=desired[i]
        if alive and abs(sig-old_signal)>1e-12:
            new_qty=(leverage*sig*max(cash_open,0.)/op) if sig!=0 else 0.0
            traded=abs(new_qty-qty)*op
            cash_open-=fee*traded
            qty=new_qty; old_signal=sig
        if alive and qty!=0:
            if qty>0:
                liq_price=(op-cash_open/qty)/(1-MMR)
                hit=(liq_price>0 and lo<=liq_price)
            else:
                n=-qty; liq_price=(op+cash_open/n)/(1+MMR)
                hit=(hi>=liq_price)
            if hit:
                notional=abs(qty*liq_price)
                cash=max(0.,notional*(MMR-liq_fee))
                eq[i]=cash; pnl[i]=cash/(eq[i-1] if i else 1.)-1
                liquidated=True; liq_i=i; alive=False; qty=0.; prev_close=cl
                continue
        if alive:
            cash=cash_open + qty*(cl-op)
            # At this candle's close, funding applies to the position held through the interval.
            cash-=qty*cl*fund[i]
            if cash<=0:
                cash=0.; alive=False; qty=0.
            eq[i]=cash
            prev_close=cl
            pnl[i]=eq[i]/(eq[i-1] if i else 1.)-1
        else:
            eq[i]=eq[i-1] if i else 0.; pnl[i]=0.
    return pnl,eq,liquidated,liq_i,desired
def metrics(df,eq,period):
    label,start,end=period; start=pd.Timestamp(start,tz='UTC'); mask=df.index>=start
    if end:mask &= df.index<pd.Timestamp(end,tz='UTC')
    x=eq[np.asarray(mask)]
    if len(x)<2:return None
    # Treat each 4h observation as 1/6 day; reset equity at period start.
    vals=x/x[0]; years=(len(vals)-1)/(6*365.25)
    dailyret=pd.Series(vals).pct_change().dropna(); sd=dailyret.std(ddof=1)
    return {'period':label,'start':df.index[mask][0].date().isoformat(),'end':df.index[mask][-1].date().isoformat(),'bars':len(vals),'CAGR':vals[-1]**(1/years)-1 if years>0 and vals[-1]>0 else -1.,'Sharpe':dailyret.mean()/sd*np.sqrt(6*365.25) if sd>0 else np.nan,'MaxDD':(vals/np.maximum.accumulate(vals)-1).min()}

# Load 4h perp + funding + spot for BTC/ETH.
assets={}
for sym in ['BTCUSDT','ETHUSDT']:
    d=pd.read_csv(ROOT/f'{sym.lower()}_fut_4h.csv',parse_dates=['open_time','close_time']).set_index('open_time').sort_index(); d.index=pd.to_datetime(d.index,utc=True)
    spot=pd.read_csv(ROOT/f'{sym.lower()}_spot_4h.csv',parse_dates=['open_time','close_time']).set_index('open_time').sort_index(); spot.index=pd.to_datetime(spot.index,utc=True)
    car=pd.read_csv(ROOT/f'{sym.lower()}_carry_4h.csv',index_col=0,parse_dates=True); car.index=pd.to_datetime(car.index,utc=True); funding=car.funding
    f=pd.Series(funding.reindex(d.index+pd.Timedelta(hours=4)).to_numpy(),index=d.index)
    assets[sym]=(d,spot,f)

records=[]; signals_by={}; simulations={}
for sym,(d,spot,f) in assets.items():
    sigs,fr=make_4h(d,f); signals_by[sym]=sigs
    # Buy-and-hold direction and a pure short benchmark.
    sigs['BuyHold_long']=pd.Series(1.,index=d.index); sigs['BuyHold_short']=pd.Series(-1.,index=d.index)
    for name,raw in sigs.items():
        for period in PERIODS:
            label,start,end=period; start_ts=pd.Timestamp(start,tz='UTC')
            mask=d.index>=start_ts
            if end: mask &= d.index<pd.Timestamp(end,tz='UTC')
            drun=d.loc[np.asarray(mask)]
            if len(drun)<2: continue
            for lev in [1.,2.]:
                _,eq,liq,liq_i,pos=simulate(drun,raw,fr,lev)
                m=metrics(drun,eq,(label,drun.index[0].date().isoformat(),None))
                if m: records.append({'asset':sym,'strategy':name,'leverage':lev,'liquidated':liq,'liq_time':str(drun.index[liq_i]) if liq_i is not None else '',**m})
    # Select up to three ideas using training-only Sharpe, then stress 3x/5x on all later periods.
    train_rows=[r for r in records if r['asset']==sym and r['period']=='train' and r['leverage']==1. and r['strategy'] not in ['BuyHold_short','BuyHold_long'] and np.isfinite(r['Sharpe'])]
    selected=[x['strategy'] for x in sorted(train_rows,key=lambda x:x['Sharpe'],reverse=True)[:3]]
    print(sym,'training-selected for 3x/5x:',selected)
    for name in selected:
        raw=sigs[name]
        for period in PERIODS:
            label,start,end=period; mask=d.index>=pd.Timestamp(start,tz='UTC')
            if end:mask &= d.index<pd.Timestamp(end,tz='UTC')
            drun=d.loc[np.asarray(mask)]
            for lev in [3.,5.]:
                _,eq,liq,liq_i,pos=simulate(drun,raw,fr,lev)
                m=metrics(drun,eq,(label,drun.index[0].date().isoformat(),None))
                if m:records.append({'asset':sym,'strategy':name,'leverage':lev,'liquidated':liq,'liq_time':str(drun.index[liq_i]) if liq_i is not None else '',**m})
    # Funding carry: use rolling average over actual settlement events, then apply to following event interval.
    event=fr.notna(); favg=fr.loc[event].rolling(7,min_periods=7).mean(); csig=pd.Series(np.nan,index=d.index); csig.loc[event]=(favg>0).astype(float); csig=csig.ffill().fillna(0)
    for period in PERIODS:
        label,start,end=period; mask=d.index>=pd.Timestamp(start,tz='UTC')
        if end:mask &= d.index<pd.Timestamp(end,tz='UTC')
        drun=d.loc[np.asarray(mask)]
        _,eq,liq,liq_i,pos=simulate(drun,csig,fr,1.,spot=spot,carry=True)
        m=metrics(drun,eq,(label,drun.index[0].date().isoformat(),None))
        if m:records.append({'asset':sym,'strategy':'Carry7_spot_long_perp_short','leverage':1.,'liquidated':False,'liq_time':'',**m})
summary=pd.DataFrame(records); summary.to_csv(ROOT/'crazy_4h_summary.csv',index=False)
summary=pd.DataFrame(records); summary.to_csv(ROOT/'crazy_4h_summary.csv',index=False)

# Strategy 18: weekly cross-sectional 30d momentum, top-two long / bottom-two short.
# Perpetual event prices approximate daily futures closes; funding is charged per asset.
syms=['BTCUSDT','ETHUSDT','BNBUSDT','SOLUSDT']; pxs={}; fds={}
for sym in syms:
    q=pd.read_csv(ROOT/f'{sym.lower()}_carry_4h.csv',index_col=0,parse_dates=True); q.index=pd.to_datetime(q.index,utc=True)
    pxs[sym]=q.perp.groupby(q.index.floor('D')).last()
    fds[sym]=q.funding.groupby(q.index.floor('D')).sum()
prices=pd.concat(pxs,axis=1).dropna(); prices.columns=syms; r=prices.pct_change().fillna(0)
fund_daily=pd.concat(fds,axis=1).reindex(prices.index).fillna(0); fund_daily.columns=syms
score=prices.pct_change(30); targets=pd.DataFrame(np.nan,index=prices.index,columns=syms)
for i,dt in enumerate(prices.index):
    if i<30 or dt.weekday()!=0: continue
    rank=score.iloc[i-1].dropna().sort_values()
    if len(rank)<4:continue
    targets.loc[dt,rank.index[:2]]=-.25; targets.loc[dt,rank.index[-2:]]=.25
targets=targets.ffill().fillna(0).shift(1).fillna(0)
turn=targets.diff().abs().sum(axis=1).fillna(targets.abs().sum(axis=1))
portret=(targets*r).sum(axis=1)-turn*.0005-(targets*fund_daily).sum(axis=1)
benchmark=r.mean(axis=1)
for name,base in [('XSecMom30_weekly_LS',portret),('BuyHold_EW4',benchmark)]:
    for lev in ([1.,2.] if name.startswith('XSec') else [1.]):
        net=base*lev; eq=(1+net).cumprod()
        for label,a,b in [('train','2021-01-01','2024-01-01'),('test_2024_26','2024-01-01',None)]:
            x=eq.loc[eq.index>=pd.Timestamp(a,tz='UTC')]
            if b:x=x.loc[x.index<pd.Timestamp(b,tz='UTC')]
            vals=x/x.iloc[0]; years=(len(vals)-1)/365.25; dr=vals.pct_change().dropna()
            records.append({'asset':'EW4','strategy':name,'leverage':lev,'liquidated':'not modelled (daily series)','period':label,'start':x.index[0].date().isoformat(),'end':x.index[-1].date().isoformat(),'bars':len(x),'CAGR':vals.iloc[-1]**(1/years)-1,'Sharpe':dr.mean()/dr.std()*np.sqrt(365.25),'MaxDD':(vals/vals.cummax()-1).min()})
summary=pd.DataFrame(records); summary.to_csv(ROOT/'crazy_strategy_summary.csv',index=False)
print('Test period 2023+ directional 4h, leverage 1x/2x:')
print(summary.query("period=='test_2023_26' and leverage<=2").sort_values(['asset','Sharpe'],ascending=[True,False]).to_string(index=False))
print('Test 2024+ cross-sectional:')
print(summary.query("asset=='EW4' and period=='test_2024_26'").to_string(index=False))
