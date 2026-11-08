import pandas as pd, numpy as np
from pathlib import Path
root=Path(__file__).resolve().parent
bars=pd.read_csv(root/'btcusdt_ohlcv.csv',parse_dates=['date'],index_col='date')
c=bars.close; ret=c.pct_change().fillna(0)
sets={'20_60_120':[20,60,120],'30_90_180':[30,90,180],'40_120_240':[40,120,240],'60_120_252':[60,120,252]}
rows=[]
for label,hs in sets.items():
 votes=sum((c.pct_change(n)>0).astype(int) for n in hs)
 for threshold in [1,2,3]:
  sig=(votes>=threshold).astype(float); pos=sig.shift(2).fillna(0)
  for fee in [.001,.002]:
   net=pos*ret-fee*pos.diff().abs().fillna(pos.iloc[0])
   for period,a,b in [('train','2017-08-17','2023-01-01'),('validation','2023-01-01',None),('2024-now','2024-01-01',None)]:
    x=net.loc[net.index>=pd.Timestamp(a,tz='UTC')]
    if b:x=x.loc[x.index<pd.Timestamp(b,tz='UTC')]
    eq=(1+x).cumprod(); years=len(x)/365; sd=x.std(ddof=1)
    rows.append({'horizons':label,'votes_min':threshold,'period':period,'fee_bps':fee*10000,'CAGR':eq.iloc[-1]**(1/years)-1,'Sharpe':x.mean()/sd*np.sqrt(365),'Vol':sd*np.sqrt(365),'MaxDD':(eq/eq.cummax()-1).min(),'Exposure':pos.reindex(x.index).mean()})
df=pd.DataFrame(rows); df.to_csv(root/'multihorizon_sensitivity.csv',index=False)
print(df[(df.period=='validation')&(df.fee_bps==10)].sort_values('Sharpe',ascending=False).round(3).to_string(index=False))
