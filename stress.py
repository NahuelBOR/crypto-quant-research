import pandas as pd, numpy as np
from pathlib import Path
base=Path(__file__).resolve().parent
p=pd.read_csv(base/'prices_aligned.csv',parse_dates=['date'],index_col='date')
r=p.pct_change().fillna(0)
rows=[]
for sym in p.columns:
 c=p[sym]
 sigs={'BuyHold':pd.Series(1.,index=c.index),'SMA200':(c>c.rolling(200).mean()),'Mom90':(c.pct_change(90)>0)}
 for name,sig in sigs.items():
  # Conservative bar delay: signal at close t-2 earns close[t-1] -> close[t].
  pos=sig.shift(2).fillna(0).astype(float)
  for fee in [.001,.002]:
   net=pos*r[sym]-fee*pos.diff().abs().fillna(pos.iloc[0])
   for period,a,b in [('train','2021-01-01','2024-01-01'),('test','2024-01-01',None)]:
    x=net.loc[net.index>=pd.Timestamp(a,tz='UTC')]
    if b:x=x.loc[x.index<pd.Timestamp(b,tz='UTC')]
    eq=(1+x).cumprod(); y=len(x)/365
    rows.append({'asset':sym,'strategy':name,'period':period,'fee_bps':fee*10000,'cagr':eq.iloc[-1]**(1/y)-1,'sharpe':x.mean()/x.std()*np.sqrt(365),'maxdd':(eq/eq.cummax()-1).min()})
df=pd.DataFrame(rows); df.to_csv(base/'robustness.csv',index=False)
print(df[df.asset=='BTCUSDT'].to_string(index=False))
# equal-weight four-asset conservative execution portfolio
po=[]
for name in ['BuyHold','SMA200','Mom90']:
 for fee in [.001,.002]:
  ss=[]
  for sym in p.columns:
   c=p[sym]; sig={'BuyHold':pd.Series(1.,index=c.index),'SMA200':c>c.rolling(200).mean(),'Mom90':c.pct_change(90)>0}[name]
   pos=sig.shift(2).fillna(0).astype(float); ss.append(pos*r[sym]-fee*pos.diff().abs().fillna(pos.iloc[0]))
  net=pd.concat(ss,axis=1).mean(axis=1)
  for period,a,b in [('train','2021-01-01','2024-01-01'),('test','2024-01-01',None)]:
   x=net.loc[net.index>=pd.Timestamp(a,tz='UTC')]
   if b:x=x.loc[x.index<pd.Timestamp(b,tz='UTC')]
   eq=(1+x).cumprod(); y=len(x)/365
   po.append({'asset':'EW4','strategy':name,'period':period,'fee_bps':fee*10000,'cagr':eq.iloc[-1]**(1/y)-1,'sharpe':x.mean()/x.std()*np.sqrt(365),'maxdd':(eq/eq.cummax()-1).min()})
print(pd.DataFrame(po).to_string(index=False))
pd.concat([df,pd.DataFrame(po)],ignore_index=True).to_csv(base/'robustness.csv',index=False)
