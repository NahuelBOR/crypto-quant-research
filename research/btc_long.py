import requests, pandas as pd, numpy as np, time
from pathlib import Path
out=Path(__file__).resolve().parent
url='https://api.binance.com/api/v3/klines'
start=int(pd.Timestamp('2017-01-01',tz='UTC').timestamp()*1000); end=int(pd.Timestamp.now(tz='UTC').floor('D').timestamp()*1000)-1

def get(symbol):
    nonlocal_dummy=None
    st=start; rows=[]
    while st<end:
        r=requests.get(url,params={'symbol':symbol,'interval':'1d','startTime':st,'endTime':end,'limit':1000},timeout=30); r.raise_for_status(); batch=r.json()
        if not batch: break
        rows+=batch; st=batch[-1][0]+86400000
        if len(batch)<1000: break
        time.sleep(.1)
    d=pd.DataFrame(rows,columns=list(range(12))); d['date']=pd.to_datetime(d[0],unit='ms',utc=True).dt.floor('D'); d['close']=d[4].astype(float)
    d=d.loc[d.date<pd.Timestamp.now(tz='UTC').floor('D')].set_index('date').close.sort_index()
    return d
p=get('BTCUSDT'); r=p.pct_change().fillna(0)
ma=p.rolling(200).mean(); mom=p.pct_change(90)
# OOS fixed signals, one-day delay. Entry/exit uses yesterday's close.
signals={'BuyHold':pd.Series(1.,index=p.index),'SMA200':(p.shift(1)>ma.shift(1)).astype(float),'Mom90':(mom.shift(1)>0).astype(float)}
res=[]
for name,pos in signals.items():
    net=pos*r-.001*pos.diff().abs().fillna(pos.iloc[0])
    for label,a,b in [('train','2017-01-01','2023-01-01'),('test','2023-01-01',None)]:
        x=net.loc[net.index>=pd.Timestamp(a,tz='UTC')]
        if b:x=x.loc[x.index<pd.Timestamp(b,tz='UTC')]
        eq=(1+x).cumprod(); y=len(x)/365; vol=x.std()*np.sqrt(365)
        res.append({'asset':'BTCUSDT','strategy':name,'period':label,'start':x.index.min().date(),'end':x.index.max().date(),'days':len(x),'cagr':eq.iloc[-1]**(1/y)-1,'vol':vol,'sharpe':x.mean()/x.std()*np.sqrt(365),'max_drawdown':(eq/eq.cummax()-1).min(),'exposure':pos.reindex(x.index).mean()})
pd.DataFrame(res).to_csv(out/'btc_long_summary.csv',index=False)
print('history',p.index.min().date(),p.index.max().date())
print(pd.DataFrame(res).to_string(index=False))
