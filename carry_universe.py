import time, requests
import numpy as np, pandas as pd
from pathlib import Path
ROOT=Path(__file__).resolve().parent
SPOT='https://api.binance.com/api/v3/klines'; FUT='https://fapi.binance.com/fapi/v1/klines'; FUND='https://fapi.binance.com/fapi/v1/fundingRate'
SYMBOLS=['BTCUSDT','ETHUSDT','BNBUSDT','SOLUSDT']; START=int(pd.Timestamp('2019-01-01',tz='UTC').timestamp()*1000); NOW=int(pd.Timestamp.now(tz='UTC').timestamp()*1000)

def get_klines(url,symbol,limit):
 rows=[]; st=START
 while st<NOW:
  r=requests.get(url,params={'symbol':symbol,'interval':'4h','startTime':st,'endTime':NOW,'limit':limit},timeout=30); r.raise_for_status(); batch=r.json()
  if not batch: break
  rows.extend(batch); st=batch[-1][0]+1
  if len(batch)<limit: break
  time.sleep(.08)
 d=pd.DataFrame(rows,columns=range(12)); d['open_time']=pd.to_datetime(d[0],unit='ms',utc=True); d['settle_time']=d.open_time+pd.Timedelta(hours=4); d['close']=pd.to_numeric(d[4]); d['close_time_ms']=pd.to_numeric(d[6]); d=d.loc[d.close_time_ms<NOW].drop_duplicates('settle_time').set_index('settle_time').sort_index()
 return d.close

def get_funding(symbol):
 rows=[]; st=START
 while st<NOW:
  r=requests.get(FUND,params={'symbol':symbol,'startTime':st,'endTime':NOW,'limit':1000},timeout=30); r.raise_for_status(); batch=r.json()
  if not batch: break
  rows+=batch; st=int(batch[-1]['fundingTime'])+1
  if len(batch)<1000: break
  time.sleep(.08)
 f=pd.DataFrame(rows)
 if f.empty:return pd.Series(dtype=float)
 f['time']=pd.to_datetime(f.fundingTime.astype('int64'),unit='ms',utc=True).dt.floor('s'); f['rate']=f.fundingRate.astype(float)
 return f.drop_duplicates('time').set_index('time').rate.sort_index()

records=[]
for sym in SYMBOLS:
 spot=get_klines(SPOT,sym,1000); perp=get_klines(FUT,sym,1500); funding=get_funding(sym)
 d=pd.concat([spot.rename('spot'),perp.rename('perp'),funding.rename('funding')],axis=1).dropna().sort_index()
 d.to_csv(ROOT/f'{sym.lower()}_carry_4h.csv')
 if len(d)<100:continue
 sr=d.spot.pct_change().fillna(0); pr=d.perp.pct_change().fillna(0)
 # Decisions use only completed funding payments. Positive funding => long spot and short perp.
 for rule,n in [('last',1),('mean3',3),('mean7',7)]:
  avg=d.funding if n==1 else d.funding.rolling(n).mean()
  pos=(avg>0).astype(float).shift(1).fillna(0)
  basis=pos*(sr-pr); carry=pos*d.funding; turn=pos.diff().abs().fillna(abs(pos.iloc[0]))
  for fee_spot,fee_fut,fee_label in [(.001,.0005,'standard'),(.002,.001,'double')]:
   costs=turn*(fee_spot+fee_fut)
   # PnL divided by 2: account return on one unit of spot plus one unit of perp gross exposure.
   net=(basis+carry-costs)/2
   for period,a,b in [('train','2020-01-01','2023-01-01'),('validation','2023-01-01',None),('2024-now','2024-01-01',None)]:
    x=net.loc[net.index>=pd.Timestamp(a,tz='UTC')]
    if b:x=x.loc[x.index<pd.Timestamp(b,tz='UTC')]
    if len(x)<30:continue
    eq=(1+x).cumprod(); years=(x.index[-1]-x.index[0]).total_seconds()/(365.25*24*3600); events_per_year=len(x)/years; sd=x.std(ddof=1)
    records.append({'asset':sym,'rule':rule,'period':period,'cost_case':fee_label,'start':x.index[0].isoformat(),'end':x.index[-1].isoformat(),'funding_events':len(x),'CAGR_per_gross_capital':eq.iloc[-1]**(1/years)-1,'Sharpe':x.mean()/sd*np.sqrt(events_per_year),'Vol':sd*np.sqrt(6*365),'MaxDD':(eq/eq.cummax()-1).min(),'active_fraction':pos.loc[x.index].mean(),'avg_funding_APR_active':d.funding.loc[x.index][pos.loc[x.index]>0].sum()/years if (pos.loc[x.index]>0).any() else np.nan,'carry_ann_contribution':carry.loc[x.index].sum()/years/2,'basis_ann_contribution':basis.loc[x.index].sum()/years/2,'cost_ann_contribution':-costs.loc[x.index].sum()/years/2})
 print(sym,'events',len(d),'range',d.index.min(),d.index.max())
res=pd.DataFrame(records);res.to_csv(ROOT/'carry_universe_summary.csv',index=False)
print(res.query("cost_case=='standard' and period=='validation'").sort_values(['asset','rule']).to_string(index=False))


