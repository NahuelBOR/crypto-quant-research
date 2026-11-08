import requests,pandas as pd,numpy as np,time
u='https://api.binance.com/api/v3/klines'; st=int(pd.Timestamp('2017-01-01',tz='UTC').timestamp()*1000); end=int(pd.Timestamp.now(tz='UTC').floor('D').timestamp()*1000)-1; rr=[]
while st<end:
 b=requests.get(u,params={'symbol':'BTCUSDT','interval':'1d','startTime':st,'endTime':end,'limit':1000},timeout=30).json()
 if not b:break
 rr+=b;st=b[-1][0]+86400000
 if len(b)<1000:break
 time.sleep(.1)
d=pd.DataFrame(rr); d['date']=pd.to_datetime(d[0],unit='ms',utc=True).dt.floor('D'); p=pd.Series(d[4].astype(float).values,index=d.date); ret=p.pct_change().fillna(0); sig={'BuyHold':pd.Series(1.,index=p.index),'SMA200':p>p.rolling(200).mean()}
for lag in [1,2]:
 for fee in [.001,.002]:
  for name,s in sig.items():
   pos=s.shift(lag).fillna(0); net=pos*ret-fee*pos.diff().abs().fillna(pos.iloc[0]); x=net.loc[net.index>=pd.Timestamp('2023-01-01',tz='UTC')]; eq=(1+x).cumprod(); years=len(x)/365
   print(lag,fee*1e4,name,round(eq.iloc[-1]**(1/years)-1,4),round(x.mean()/x.std()*np.sqrt(365),3),round((eq/eq.cummax()-1).min(),4))
