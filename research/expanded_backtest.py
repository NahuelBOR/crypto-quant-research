import time, requests
import numpy as np
import pandas as pd
from pathlib import Path

ROOT = Path(__file__).resolve().parent
URL = 'https://api.binance.com/api/v3/klines'
SYMBOLS = ['BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'SOLUSDT']
START = int(pd.Timestamp('2017-01-01', tz='UTC').timestamp() * 1000)
END = int(pd.Timestamp.now(tz='UTC').floor('D').timestamp() * 1000) - 1
FEE = 0.001
LAG = 2  # next-close fill proxy, then close-to-close return


def fetch(symbol):
    rows, start = [], START
    while start < END:
        r = requests.get(URL, params={'symbol': symbol, 'interval': '1d', 'startTime': start, 'endTime': END, 'limit': 1000}, timeout=30)
        r.raise_for_status()
        batch = r.json()
        if not batch: break
        rows.extend(batch)
        start = batch[-1][0] + 86_400_000
        if len(batch) < 1000: break
        time.sleep(.12)
    df = pd.DataFrame(rows, columns=['open_time','open','high','low','close','volume','close_time','quote_volume','trades','taker_base','taker_quote','ignore'])
    df['date'] = pd.to_datetime(df.open_time, unit='ms', utc=True).dt.floor('D')
    for c in ['open','high','low','close','volume']:
        df[c] = pd.to_numeric(df[c])
    df = df.loc[df.date < pd.Timestamp.now(tz='UTC').floor('D')].drop_duplicates('date').set_index('date').sort_index()
    df[['open','high','low','close','volume']].to_csv(ROOT / f'{symbol.lower()}_ohlcv.csv')
    return df[['open','high','low','close','volume']]


def rsi(c, n):
    d=c.diff(); up=d.clip(lower=0).ewm(alpha=1/n,adjust=False,min_periods=n).mean(); dn=(-d.clip(upper=0)).ewm(alpha=1/n,adjust=False,min_periods=n).mean()
    rs=up/dn.replace(0,np.nan)
    return 100-100/(1+rs)


def state_signal(index, entry, exit_):
    out=pd.Series(0.0,index=index); held=0.0
    for i in range(len(index)):
        en=entry.iloc[i]; ex=exit_.iloc[i]
        if held==0 and bool(en): held=1.0
        elif held==1 and bool(ex): held=0.0
        out.iloc[i]=held
    return out


def make_signals(df):
    c,h,l=df.close,df.high,df.low
    s={}
    s['BuyHold']=pd.Series(1.0,index=c.index)
    s['SMA200']=(c>c.rolling(200).mean())*1.0
    s['SMA50_200']=(c.rolling(50).mean()>c.rolling(200).mean())*1.0
    s['EMA50_200']=(c.ewm(span=50,adjust=False).mean()>c.ewm(span=200,adjust=False).mean())*1.0
    s['Mom90']=(c.pct_change(90)>0)*1.0
    # 12-1 month time-series momentum: 12-month return excluding the most recent month.
    s['Mom12_1']=((c.shift(21)/c.shift(252)-1)>0)*1.0
    mom=[c.pct_change(n)>0 for n in [30,90,180]]
    s['MultiHorizon']=(sum(x.astype(int) for x in mom)>=2)*1.0
    macd=c.ewm(span=12,adjust=False).mean()-c.ewm(span=26,adjust=False).mean()
    s['MACD']=(macd>macd.ewm(span=9,adjust=False).mean())*1.0
    s['Donchian55_20']=state_signal(c.index,h>h.rolling(55).max().shift(1),l<l.rolling(20).min().shift(1))
    rr=rsi(c,2)
    s['RSI2_MR']=state_signal(c.index,rr<10,rr>50)
    rr=rsi(c,14)
    s['RSI14_MR']=state_signal(c.index,rr<30,rr>55)
    ma=c.rolling(20).mean(); sd=c.rolling(20).std(ddof=0)
    # Enter below lower Bollinger band; exit at the rolling midline.
    s['Bollinger20_MR']=state_signal(c.index,c<ma-2*sd,c>=ma)
    # Volatility scaling, estimates use closes through yesterday. No leverage; maximum spot exposure is 100%.
    rv=c.pct_change().rolling(30).std().shift(1)*np.sqrt(365)
    s['VolTarget20']=pd.Series(np.minimum(1.0,0.20/rv),index=c.index).replace([np.inf,-np.inf],np.nan).fillna(0)
    s['SMA200_Vol20']=s['SMA200']*s['VolTarget20']
    s['SMA200_Vol30']=s['SMA200']*pd.Series(np.minimum(1.0,0.30/rv),index=c.index).replace([np.inf,-np.inf],np.nan).fillna(0)
    return {k:pd.Series(v,index=c.index).astype(float) for k,v in s.items()}


def score(returns, pos, start, end=None, fee=FEE):
    p=pos.shift(LAG).fillna(0.0)
    turnover=p.diff().abs().fillna(abs(p.iloc[0]))
    net=p*returns-fee*turnover
    mask=net.index>=pd.Timestamp(start,tz='UTC')
    if end is not None: mask &= net.index<pd.Timestamp(end,tz='UTC')
    x=net.loc[mask]
    if len(x)<2:return None
    eq=(1+x).cumprod(); years=len(x)/365.0; sd=x.std(ddof=1)
    return {'start':x.index[0].date().isoformat(),'end':x.index[-1].date().isoformat(),'days':len(x),'CAGR':eq.iloc[-1]**(1/years)-1,'Sharpe':x.mean()/sd*np.sqrt(365) if sd else np.nan,'Vol':sd*np.sqrt(365),'MaxDD':(eq/eq.cummax()-1).min(),'Exposure':p.loc[x.index].mean(),'TurnoverPerYear':turnover.loc[x.index].sum()/years,'net':net,'pos':p}

frames={s:fetch(s) for s in SYMBOLS}
signals_by={s:make_signals(df) for s,df in frames.items()}
records=[]; returns_by={}; pos_by={}
periods=[('train','2017-08-17','2023-01-01'),('validation','2023-01-01',None)]
for symbol,df in frames.items():
    ret=df.close.pct_change().fillna(0)
    for name,pos in signals_by[symbol].items():
        returns_by[(symbol,name)]=ret
        pos_by[(symbol,name)]=pos
        for period,a,b in periods:
            for fee_bps in [10,20]:
                m=score(ret,pos,a,b,fee_bps/10000)
                if m:
                    records.append({'asset':symbol,'strategy':name,'period':period,'fee_bps':fee_bps,**{k:v for k,v in m.items() if k not in ['net','pos']}})

# BTC year-by-year regimes, one row per fixed strategy at 10/20 bps.
btc=frames['BTCUSDT']; btcret=btc.close.pct_change().fillna(0); btcsigs=signals_by['BTCUSDT']
for name,pos in btcsigs.items():
    for period,a,b in [('2018-2020','2018-01-01','2021-01-01'),('2021-2023','2021-01-01','2024-01-01'),('2024-now','2024-01-01',None)]:
        for fee_bps in [10,20]:
            m=score(btcret,pos,a,b,fee_bps/10000)
            if m: records.append({'asset':'BTCUSDT','strategy':name,'period':period,'fee_bps':fee_bps,**{k:v for k,v in m.items() if k not in ['net','pos']}})

summary=pd.DataFrame(records)
summary.to_csv(ROOT/'expanded_backtest_summary.csv',index=False)

# Equal-weight four-sleeve buy-and-hold and strategies from 2021 onward; diagnostic only due current-universe bias.
common=pd.concat([frames[s].close.rename(s) for s in SYMBOLS],axis=1).dropna()
port=[]
for name in signals_by['BTCUSDT'].keys():
    for period,a,b in [('train','2021-01-01','2024-01-01'),('validation','2024-01-01',None)]:
        for fee_bps in [10,20]:
            sleeves=[]
            for s in SYMBOLS:
                d=frames[s]; ret=d.close.pct_change().fillna(0); pos=signals_by[s][name]
                q=score(ret,pos,a,b,fee_bps/10000)
                if q is not None: sleeves.append(q['net'].rename(s))
            pnet=pd.concat(sleeves,axis=1).mean(axis=1).dropna()
            pnet=pnet.loc[pnet.index>=pd.Timestamp(a,tz='UTC')]
            if b is not None: pnet=pnet.loc[pnet.index<pd.Timestamp(b,tz='UTC')]
            eq=(1+pnet).cumprod(); years=len(pnet)/365; sd=pnet.std(ddof=1)
            port.append({'asset':'EW4','strategy':name,'period':period,'fee_bps':fee_bps,'start':pnet.index[0].date().isoformat(),'end':pnet.index[-1].date().isoformat(),'days':len(pnet),'CAGR':eq.iloc[-1]**(1/years)-1,'Sharpe':pnet.mean()/sd*np.sqrt(365),'Vol':sd*np.sqrt(365),'MaxDD':(eq/eq.cummax()-1).min()})
pd.DataFrame(port).to_csv(ROOT/'expanded_ew4_summary.csv',index=False)

# Paired circular moving-block bootstrap vs BTC buy-and-hold, 30-day blocks, 5000 draws.
# Uses net daily returns after the conservative fill delay and 10 bps fee.
base=score(btcret,btcsigs['BuyHold'],'2023-01-01',None,0.001)['net']
bootrows=[]; rng=np.random.default_rng(20261106); B=5000; block=30
for name,pos in btcsigs.items():
    if name=='BuyHold': continue
    strat=score(btcret,pos,'2023-01-01',None,0.001)['net']
    diff=(strat-base).dropna().to_numpy(); n=len(diff); nblocks=int(np.ceil(n/block)); samples=np.empty(B)
    for j in range(B):
        starts=rng.integers(0,n,size=nblocks)
        ix=np.concatenate([(np.arange(st,st+block)%n) for st in starts])[:n]
        samples[j]=diff[ix].mean()*365
    bootrows.append({'strategy':name,'mean_annualized_arithmetic_diff':diff.mean()*365,'prob_positive_diff':(samples>0).mean(),'ci95_low':np.quantile(samples,.025),'ci95_high':np.quantile(samples,.975)})
pd.DataFrame(bootrows).to_csv(ROOT/'expanded_block_bootstrap.csv',index=False)

print('data:',{s:(f.index.min().date().isoformat(),f.index.max().date().isoformat(),len(f)) for s,f in frames.items()})
print('\nBTC 2023+ validation, fee 10bps, conservative lag:')
print(summary.query("asset=='BTCUSDT' and period=='validation' and fee_bps==10").sort_values('Sharpe',ascending=False).to_string(index=False))
print('\nBTC regime returns 2024-now, fee 10bps:')
print(summary.query("asset=='BTCUSDT' and period=='2024-now' and fee_bps==10").sort_values('Sharpe',ascending=False).to_string(index=False))
print('\nBootstrap:')
print(pd.read_csv(ROOT/'expanded_block_bootstrap.csv').sort_values('prob_positive_diff',ascending=False).to_string(index=False))


