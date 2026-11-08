import numpy as np
import pandas as pd
from pathlib import Path

ROOT=Path(__file__).resolve().parent
MMR=.005; LIQ_FEE=.002

def pulse(index,trig,hold):
    out=np.zeros(len(index)); active=0
    for i,x in enumerate(trig.fillna(False).to_numpy()):
        if x: active=hold
        if active: out[i]=1.; active-=1
    return pd.Series(out,index=index)

def sim(df,raw,fund,lev=1.,fee=.0005):
    desired=raw.shift(1).reindex(df.index).fillna(0).to_numpy(float)
    f=fund.reindex(df.index).fillna(0).to_numpy(float)
    op,hi,lo,cl=(df[k].to_numpy(float) for k in ('open','high','low','close'))
    cash=1.; qty=0.; prev=None; eq=np.ones(len(df)); dead=False
    for i in range(len(df)):
        co=cash+(qty*(op[i]-prev) if prev is not None else 0.)
        sig=desired[i]
        nq=lev*sig*max(co,0)/op[i] if sig else 0.
        if nq!=qty: co-=fee*abs(nq-qty)*op[i]; qty=nq
        if qty>0:
            lp=(op[i]-co/qty)/(1-MMR); hit=lp>0 and lo[i]<=lp
        elif qty<0:
            lp=(op[i]+co/(-qty))/(1+MMR); hit=hi[i]>=lp
        else: hit=False
        if hit:
            cash=max(0.,abs(qty*lp)*(MMR-LIQ_FEE)); eq[i:]=cash; dead=True; break
        cash=co+qty*(cl[i]-op[i])-qty*cl[i]*f[i]
        eq[i]=max(0.,cash); prev=cl[i]
    years=max(1,len(df)-1)/(6*365.25); r=pd.Series(eq).pct_change().dropna()
    cagr=eq[-1]**(1/years)-1 if eq[-1]>0 else -1
    sharpe=r.mean()/r.std(ddof=1)*np.sqrt(6*365.25) if r.std(ddof=1) else np.nan
    dd=(eq/np.maximum.accumulate(eq)-1).min()
    return cagr,sharpe,dd,dead

periods=[('train','2020-01-01','2023-01-01'),('2023','2023-01-01','2024-01-01'),('2024_25','2024-01-01','2026-01-01'),('2026_ytd','2026-01-01',None),('test_2023_26','2023-01-01',None)]
rows=[]
for sym in ('BTCUSDT','ETHUSDT'):
    d=pd.read_csv(ROOT/f'{sym.lower()}_fut_4h.csv',parse_dates=['open_time']).set_index('open_time').sort_index(); d.index=pd.to_datetime(d.index,utc=True)
    c=pd.read_csv(ROOT/f'{sym.lower()}_carry_4h.csv',index_col=0,parse_dates=True); c.index=pd.to_datetime(c.index,utc=True)
    f=pd.Series(c.funding.reindex(d.index+pd.Timedelta(hours=4)).to_numpy(),index=d.index)
    mom=d.close.pct_change(6); vz=(d.volume-d.volume.rolling(30).mean())/d.volume.rolling(30).std(ddof=1)
    for thr in (.06,.08,.10):
      for volz in (1.,1.5,2.):
       for hold in (1,2,3):
        raw=pulse(d.index,(mom < -thr)&(vz>volz),hold)
        for label,start,end in periods:
            mask=d.index>=pd.Timestamp(start,tz='UTC')
            if end:mask &= d.index<pd.Timestamp(end,tz='UTC')
            x=d.loc[mask]; ff=f.reindex(x.index)
            cg,sh,dd,liq=sim(x,raw.reindex(x.index),ff)
            rows.append(dict(asset=sym,loss_trigger=thr,volume_z=volz,hold_4h=hold,period=label,leverage=1,fee_bps=5,CAGR=cg,Sharpe=sh,MaxDD=dd,liquidated=liq))
        if (thr,volz,hold)==(.08,1.5,2):
            for lev,fee in ((1,.001),(2,.0005),(2,.001)):
                mask=d.index>=pd.Timestamp('2023-01-01',tz='UTC'); x=d.loc[mask]; ff=f.reindex(x.index)
                cg,sh,dd,liq=sim(x,raw.reindex(x.index),ff,lev,fee)
                rows.append(dict(asset=sym,loss_trigger=thr,volume_z=volz,hold_4h=hold,period='test_2023_26',leverage=lev,fee_bps=fee*1e4,CAGR=cg,Sharpe=sh,MaxDD=dd,liquidated=liq))
out=pd.DataFrame(rows); out.to_csv(ROOT/'crash_fade_sensitivity.csv',index=False)
print('TEST top by training Sharpe, then its held-out metrics:')
for sym in ('BTCUSDT','ETHUSDT'):
    tr=out[(out.asset==sym)&(out.period=='train')].sort_values('Sharpe',ascending=False).head(5)
    print('\n',sym,'\n',tr.to_string(index=False))
    for _,r in tr.head(3).iterrows():
        filt=(out.asset==sym)&(out.loss_trigger==r.loss_trigger)&(out.volume_z==r.volume_z)&(out.hold_4h==r.hold_4h)&(out.period.isin(['2023','2024_25','2026_ytd','test_2023_26']))
        print(out.loc[filt].to_string(index=False))
print('\nReference exact rule:')
print(out[(out.loss_trigger==.08)&(out.volume_z==1.5)&(out.hold_4h==2)].to_string(index=False))
