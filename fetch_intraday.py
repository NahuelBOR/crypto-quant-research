import time,requests,pandas as pd
from pathlib import Path
ROOT=Path(__file__).resolve().parent; NOW=int(pd.Timestamp.now(tz='UTC').timestamp()*1000)
URLS={'spot':'https://api.binance.com/api/v3/klines','fut':'https://fapi.binance.com/fapi/v1/klines'}

def klines(symbol,kind,interval,start_date,limit):
 start=int(pd.Timestamp(start_date,tz='UTC').timestamp()*1000); rows=[]; url=URLS[kind]
 while start<NOW:
  r=requests.get(url,params={'symbol':symbol,'interval':interval,'startTime':start,'endTime':NOW,'limit':limit},timeout=30); r.raise_for_status(); batch=r.json()
  if not batch:break
  rows.extend(batch); start=int(batch[-1][0])+1
  if len(batch)<limit:break
  time.sleep(.06)
 d=pd.DataFrame(rows,columns=range(12)); d['open_time']=pd.to_datetime(d[0],unit='ms',utc=True); d['close_time']=pd.to_datetime(d[6],unit='ms',utc=True); d=d.loc[d[6].astype('int64')<NOW].drop_duplicates('open_time').set_index('open_time').sort_index()
 d=d.rename(columns={1:'open',2:'high',3:'low',4:'close',5:'volume'}); d[['open','high','low','close','volume']]=d[['open','high','low','close','volume']].astype(float)
 d[['open','high','low','close','volume','close_time']].to_csv(ROOT/f'{symbol.lower()}_{kind}_{interval}.csv')
 print(symbol,kind,interval,len(d),d.index.min(),d.index.max())

for symbol in ['BTCUSDT','ETHUSDT']:
 for kind in ['spot','fut']:
  klines(symbol,kind,'4h','2020-01-01',1500 if kind=='fut' else 1000)
 klines(symbol,'fut','1h','2022-01-01',1500)
