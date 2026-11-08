import time, requests
import numpy as np, pandas as pd
from pathlib import Path
ROOT=Path(__file__).resolve().parent
SPOT='https://api.binance.com/api/v3/klines'; FUT='https://fapi.binance.com/fapi/v1/klines'; FUND='https://fapi.binance.com/fapi/v1/fundingRate'
SYMBOL='BTCUSDT'; start=int(pd.Timestamp('2019-01-01',tz='UTC').timestamp()*1000); now=int(pd.Timestamp.now(tz='UTC').timestamp()*1000)

def get_klines(url,limit):
 rows=[]; st=start
 while st<now:
  r=requests.get(url,params={'symbol':SYMBOL,'interval':'8h','startTime':st,'endTime':now,'limit':limit},timeout=30); r.raise_for_status(); batch=r.json()
  if not batch: break
  rows.extend(batch); st=batch[-1][0]+1
  if len(batch)<limit: break
  time.sleep(.1)
 d=pd.DataFrame(rows,columns=range(12)); d['open_time']=pd.to_datetime(d[0],unit='ms',utc=True); d['settle_time']=d.open_time+pd.Timedelta(hours=8)
 d['close']=pd.to_numeric(d[4]); d['close_time_ms']=pd.to_numeric(d[6]); d=d.loc[d.close_time_ms<now].drop_duplicates('settle_time').set_index('settle_time').sort_index()
 return d.close

spot=get_klines(SPOT,1000).rename('spot'); perp=get_klines(FUT,1500).rename('perp')
rows=[]; st=start
while st<now:
 r=requests.get(FUND,params={'symbol':SYMBOL,'startTime':st,'endTime':now,'limit':1000},timeout=30); r.raise_for_status(); batch=r.json()
 if not batch: break
 rows+=batch; st=int(batch[-1]['fundingTime'])+1
 if len(batch)<1000: break
 time.sleep(.1)
f=pd.DataFrame(rows); f['time']=pd.to_datetime(f.fundingTime.astype('int64'),unit='ms',utc=True).dt.floor('s'); f['rate']=f.fundingRate.astype(float); f=f.drop_duplicates('time').set_index('time').sort_index()
# Keep funding events with a completed spot and perpetual candle ending at that settlement time.
d=pd.concat([spot,perp,f.rate.rename('funding')],axis=1).dropna().sort_index()
d.to_csv(ROOT/'btc_carry_8h.csv')
# Positive funding: long spot, short one perpetual; positions for each interval use only rates observed at the preceding settlement.
rows=[]
for rule,signal in {
 'positive_last_rate':(d.funding>0).astype(float),
 'positive_mean_3':(d.funding.rolling(3).mean()>0).astype(float),
 'positive_mean_7':(d.funding.rolling(7).mean()>0).astype(float),
}.items():
 pos=signal.shift(1).fillna(0)
 spotret=d.spot.pct_change().fillna(0); perpret=d.perp.pct_change().fillna(0)
 basis=pos*(spotret-perpret); carry=pos*d.funding
 # Per 1 unit of each leg, 10 bp spot taker + 5 bp futures taker fee per traded notional.
 turn=pos.diff().abs().fillna(abs(pos.iloc[0])); cost=turn*(.0010+.0005)
 # Divide by gross 2-leg capital so reported performance is per dollar of fully funded gross exposure.
 net=(basis+carry-cost)/2
 for period,a,b in [('train','2019-09-01','2023-01-01'),('validation','2023-01-01',None),('2024-now','2024-01-01',None)]:
  x=net.loc[net.index>=pd.Timestamp(a,tz='UTC')]
  if b:x=x.loc[x.index<pd.Timestamp(b,tz='UTC')]
  eq=(1+x).cumprod(); years=len(x)/(3*365); sd=x.std(ddof=1)
  rows.append({'strategy':rule,'period':period,'start':x.index.min().isoformat(),'end':x.index.max().isoformat(),'events':len(x),'CAGR_gross_capital':eq.iloc[-1]**(1/years)-1,'Sharpe':x.mean()/sd*np.sqrt(3*365),'Vol':sd*np.sqrt(3*365),'MaxDD':(eq/eq.cummax()-1).min(),'active_fraction':pos.loc[x.index].mean(),'avg_funding_APR_if_active':(d.funding.loc[x.index][pos.loc[x.index]>0].mean()*3*365 if (pos.loc[x.index]>0).any() else np.nan),'carry_contrib_annualized':carry.loc[x.index].mean()*3*365/2,'basis_contrib_annualized':basis.loc[x.index].mean()*3*365/2,'cost_contrib_annualized':-cost.loc[x.index].mean()*3*365/2})
res=pd.DataFrame(rows); res.to_csv(ROOT/'btc_carry_summary.csv',index=False)
print('sample',d.index.min(),d.index.max(),len(d),'funding rows',len(f)); print(res.to_string(index=False))

