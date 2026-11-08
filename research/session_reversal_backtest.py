import numpy as np
import pandas as pd
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FEE = 0.0005
MMR = 0.005
LIQ_FEE = 0.002


def pulse(index, trigger, side, hold):
    a = np.zeros(len(index))
    trig = trigger.fillna(False).to_numpy()
    out = np.zeros(len(index))
    left = 0
    p = 0.0
    for i in range(len(index)):
        if trig[i]:
            left, p = hold, side[i]
        if left:
            out[i] = p
            left -= 1
    return pd.Series(out, index=index)


def simulate(df, raw, funding, leverage=1.0, fee=FEE):
    desired = raw.shift(1).reindex(df.index).fillna(0).to_numpy(float)
    fund = funding.reindex(df.index).fillna(0).to_numpy(float)
    op, hi, lo, cl = (df[x].to_numpy(float) for x in ('open', 'high', 'low', 'close'))
    cash, qty, old, prev = 1.0, 0.0, 0.0, None
    equity = np.ones(len(df)); liquidated = False; liq_time = ''
    for i in range(len(df)):
        copen = cash + (qty * (op[i] - prev) if prev is not None else 0.0)
        sig = desired[i]
        if abs(sig-old) > 1e-12:
            newqty = leverage * sig * max(copen, 0) / op[i] if sig else 0.0
            copen -= fee * abs(newqty-qty) * op[i]
            qty, old = newqty, sig
        if qty > 0:
            lp = (op[i] - copen/qty)/(1-MMR)
            hit = lp > 0 and lo[i] <= lp
        elif qty < 0:
            lp = (op[i] + copen/(-qty))/(1+MMR)
            hit = hi[i] >= lp
        else:
            hit = False
        if hit:
            cash = max(0, abs(qty*lp)*(MMR-LIQ_FEE))
            equity[i] = cash
            liquidated, liq_time = True, str(df.index[i])
            qty = 0
            if i+1 < len(equity): equity[i+1:] = cash
            break
        cash = copen + qty*(cl[i]-op[i]) - qty*cl[i]*fund[i]
        equity[i] = max(0, cash)
        prev = cl[i]
    return equity, liquidated, liq_time


def metrics(df, eq):
    vals = eq / eq[0]
    years = (len(vals)-1)/8760.0
    r = pd.Series(vals).pct_change().dropna()
    return ((vals[-1]**(1/years)-1) if years > 0 and vals[-1] > 0 else -1,
            r.mean()/r.std(ddof=1)*np.sqrt(8760) if r.std(ddof=1) else np.nan,
            (vals/np.maximum.accumulate(vals)-1).min())


rows=[]
for sym in ('BTCUSDT','ETHUSDT'):
    d=pd.read_csv(ROOT/f'{sym.lower()}_fut_1h.csv',parse_dates=['open_time']).set_index('open_time').sort_index()
    d.index=pd.to_datetime(d.index,utc=True)
    carry=pd.read_csv(ROOT/f'{sym.lower()}_carry_4h.csv',index_col=0,parse_dates=True); carry.index=pd.to_datetime(carry.index,utc=True)
    # Funding event timestamps are aligned to 4h closes; use exact observed event timestamps.
    funding=pd.Series(carry.funding.dropna().values,index=carry.funding.dropna().index)
    funding_hour=pd.Series(0.0,index=d.index)
    for t,v in funding.items():
        j=d.index.get_indexer([t],method='nearest')[0]
        if abs((d.index[j]-t).total_seconds()) <= 3600: funding_hour.iloc[j]=v
    c=d.close; h=c.pct_change(12)
    trigger=pd.Series((d.index.hour%12==11),index=d.index)
    side=(-np.sign(h)).fillna(0).to_numpy()
    raw=pulse(d.index,trigger,side,12)
    for lev in (1.,2.,3.):
        for fee in (FEE,0.001):
            for label,start,end in [('train','2022-01-01','2024-01-01'),('test_2024_26','2024-01-01',None)]:
                mask=d.index>=pd.Timestamp(start,tz='UTC')
                if end: mask &= d.index<pd.Timestamp(end,tz='UTC')
                x=d.loc[mask]; f=funding_hour.reindex(x.index)
                eq,liq,lt=simulate(x,raw.reindex(x.index),f,lev,fee)
                cg,sh,dd=metrics(x,eq)
                rows.append(dict(asset=sym,strategy='12h_session_reversal',period=label,leverage=lev,fee_bps=fee*1e4,CAGR=cg,Sharpe=sh,MaxDD=dd,liquidated=liq,liq_time=lt))
pd.DataFrame(rows).to_csv(ROOT/'session_reversal_summary.csv',index=False)
print(pd.DataFrame(rows).to_string(index=False))
