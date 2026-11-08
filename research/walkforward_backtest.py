import pandas as pd, numpy as np
from pathlib import Path
root=Path(__file__).resolve().parent
b=pd.read_csv(root/'btcusdt_ohlcv.csv',parse_dates=['date'],index_col='date'); c=b.close; h=b.high; l=b.low; ret=c.pct_change().fillna(0); idx=c.index

def rsi(x,n):
 d=x.diff(); u=d.clip(lower=0).ewm(alpha=1/n,adjust=False,min_periods=n).mean(); dn=(-d.clip(upper=0)).ewm(alpha=1/n,adjust=False,min_periods=n).mean(); rs=u/dn.replace(0,np.nan); return 100-100/(1+rs)
def state(en,ex):
 out=np.zeros(len(c)); hold=0
 ee=en.fillna(False).to_numpy(); xx=ex.fillna(False).to_numpy()
 for i in range(len(c)):
  if hold==0 and ee[i]: hold=1
  elif hold==1 and xx[i]: hold=0
  out[i]=hold
 return pd.Series(out,index=idx)
s={
'BuyHold':pd.Series(1.,index=idx),
'SMA200':(c>c.rolling(200).mean()).astype(float),
'SMA50_200':(c.rolling(50).mean()>c.rolling(200).mean()).astype(float),
'EMA50_200':(c.ewm(span=50,adjust=False).mean()>c.ewm(span=200,adjust=False).mean()).astype(float),
'Mom90':(c.pct_change(90)>0).astype(float),
'Mom12_1':((c.shift(21)/c.shift(252)-1)>0).astype(float),
'MultiHorizon':(sum((c.pct_change(n)>0).astype(int) for n in [30,90,180])>=2).astype(float),
}
macd=c.ewm(span=12,adjust=False).mean()-c.ewm(span=26,adjust=False).mean(); s['MACD']=(macd>macd.ewm(span=9,adjust=False).mean()).astype(float)
s['Donchian55_20']=state(h>h.rolling(55).max().shift(1),l<l.rolling(20).min().shift(1))
r=rsi(c,2); s['RSI2_MR']=state(r<10,r>50)
r=rsi(c,14); s['RSI14_MR']=state(r<30,r>55)
ma=c.rolling(20).mean(); sd=c.rolling(20).std(ddof=0); s['Bollinger20_MR']=state(c<ma-2*sd,c>=ma)
rv=ret.rolling(30).std().shift(1)*np.sqrt(365); s['VolTarget20']=pd.Series(np.minimum(1,.2/rv),index=idx).replace([np.inf,-np.inf],np.nan).fillna(0)
s['SMA200_Vol20']=s['SMA200']*s['VolTarget20']; s['SMA200_Vol30']=s['SMA200']*pd.Series(np.minimum(1,.3/rv),index=idx).replace([np.inf,-np.inf],np.nan).fillna(0)
pos={k:v.shift(2).fillna(0.) for k,v in s.items()}
# Candidate returns for selection all include 10 bps and the same conservative execution lag.
rets={k:p*ret-.001*p.diff().abs().fillna(p.iloc[0]) for k,p in pos.items()}
# Annual rebalance: select one strategy by trailing three calendar years' net Sharpe; first decision uses 2018-2020.
chosen=pd.Series(index=idx,dtype='object'); rows=[]
for year in range(2021,2027):
 decision=pd.Timestamp(f'{year}-01-01',tz='UTC'); train_start=pd.Timestamp(f'{year-3}-01-01',tz='UTC')
 train_end=decision
 stats={}
 for name,x in rets.items():
  q=x.loc[(x.index>=train_start)&(x.index<train_end)]
  if len(q)>300 and q.std(ddof=1)>0: stats[name]=q.mean()/q.std(ddof=1)*np.sqrt(365)
 pick=max(stats,key=stats.get)
 mask=(idx>=decision)&(idx<pd.Timestamp(f'{year+1}-01-01',tz='UTC'))
 chosen.loc[mask]=pick
 rows.append({'year':year,'train_start':train_start.date(),'selected':pick,'train_sharpe':stats[pick]})
# Position chosen by prior period model; charge costs after switching among models.
active=pd.Series(0.,index=idx)
for name in s:
 mask=chosen==name
 active.loc[mask]=pos[name].loc[mask]
turn=active.diff().abs().fillna(abs(active.iloc[0])); wf=active*ret-.001*turn
wf=wf.loc[chosen.notna()]
# Benchmarks over same dates; charge 10bps initial entry (buy/hold remains 1 after).
bh=rets['BuyHold'].loc[wf.index]
def metrics(x):
 eq=(1+x).cumprod(); years=len(x)/365; sd=x.std(ddof=1)
 return {'days':len(x),'CAGR':eq.iloc[-1]**(1/years)-1,'Sharpe':x.mean()/sd*np.sqrt(365),'Vol':sd*np.sqrt(365),'MaxDD':(eq/eq.cummax()-1).min()}
print('annual picks'); print(pd.DataFrame(rows).to_string(index=False)); print('walkforward',metrics(wf));print('buyhold',metrics(bh))
with open(root/'walkforward_selection.csv','w',newline='') as f: pd.DataFrame(rows).to_csv(f,index=False)
pd.DataFrame([{'strategy':'walk_forward_3y_sharpe',**metrics(wf)},{'strategy':'buy_hold',**metrics(bh)}]).to_csv(root/'walkforward_summary.csv',index=False)

# Paired moving-block bootstrap for the walk-forward net daily-return difference.
diff=(wf-bh).dropna().to_numpy(); rng=np.random.default_rng(20261106); B=10000; block=30; n=len(diff); nb=int(np.ceil(n/block)); draw=np.empty(B)
for j in range(B):
 starts=rng.integers(0,n,size=nb); ix=np.concatenate([(np.arange(st,st+block)%n) for st in starts])[:n]; draw[j]=diff[ix].mean()*365
print('walkforward vs BH annualized arithmetic mean diff',diff.mean()*365,'bootstrap P(diff>0)',(draw>0).mean(),'95% CI',np.quantile(draw,[.025,.975]))
pd.DataFrame({'date':wf.index,'walkforward':wf.values,'buy_hold':bh.values,'difference':diff}).to_csv(root/'walkforward_daily.csv',index=False)
