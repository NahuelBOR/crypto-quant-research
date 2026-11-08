import time, requests
import pandas as pd
import numpy as np
from pathlib import Path

BASE = Path(__file__).resolve().parent
START = int(pd.Timestamp('2021-01-01', tz='UTC').timestamp() * 1000)
END = int(pd.Timestamp.now(tz='UTC').floor('D').timestamp() * 1000) - 1
SYMBOLS = ['BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'SOLUSDT']
FEE = 0.001  # 10 bps per unit of turnover, regular-user spot fee; conservative simple model
URL = 'https://api.binance.com/api/v3/klines'


def download(symbol):
    rows, start = [], START
    while start < END:
        response = requests.get(URL, params={'symbol': symbol, 'interval': '1d', 'startTime': start, 'endTime': END, 'limit': 1000}, timeout=30)
        response.raise_for_status()
        batch = response.json()
        if not batch:
            break
        rows.extend(batch)
        start = batch[-1][0] + 86_400_000
        if len(batch) < 1000:
            break
        time.sleep(0.12)
    frame = pd.DataFrame(rows, columns=['open_time','open','high','low','close','volume','close_time','quote_volume','trades','taker_base','taker_quote','ignore'])
    frame = frame.drop_duplicates('open_time').copy()
    frame['date'] = pd.to_datetime(frame.open_time, unit='ms', utc=True).dt.floor('D')
    frame['close'] = pd.to_numeric(frame.close)
    # Drop the current, still-forming UTC daily candle.
    today = pd.Timestamp.now(tz='UTC').floor('D')
    frame = frame.loc[frame.date < today, ['date','close']].set_index('date').sort_index()
    frame.to_csv(BASE / f'{symbol.lower()}_daily.csv')
    return frame.close.rename(symbol)

prices = pd.concat([download(s) for s in SYMBOLS], axis=1).dropna()
returns = prices.pct_change().fillna(0)


def rsi(series, n=2):
    delta = series.diff()
    gain = delta.clip(lower=0).ewm(alpha=1/n, adjust=False, min_periods=n).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1/n, adjust=False, min_periods=n).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - 100 / (1 + rs)

signals = {}
for symbol in SYMBOLS:
    close = prices[symbol]
    signals[(symbol, 'BuyHold')] = pd.Series(1.0, index=prices.index)
    signals[(symbol, 'SMA200')] = (close.shift(1) > close.rolling(200).mean().shift(1)).astype(float)
    signals[(symbol, 'Mom90')] = (close.pct_change(90).shift(1) > 0).astype(float)
    # Conventional short-term mean reversion: enter on RSI(2)<10; exit on RSI(2)>50.
    signal = pd.Series(np.nan, index=prices.index)
    values = rsi(close)
    holding = 0.0
    for i in range(len(signal)):
        v = values.iloc[i-1] if i else np.nan
        if holding == 0 and pd.notna(v) and v < 10:
            holding = 1.0
        elif holding == 1 and pd.notna(v) and v > 50:
            holding = 0.0
        signal.iloc[i] = holding
    signals[(symbol, 'RSI2_MR')] = signal.fillna(0)

# Return calculations: signals use data through yesterday's close and are held for today's close-to-close return.
rows, portfolio_series = [], {}
for symbol in SYMBOLS:
    for strategy in ['BuyHold', 'SMA200', 'Mom90', 'RSI2_MR']:
        pos = signals[(symbol, strategy)].reindex(prices.index).fillna(0)
        # Buy-and-hold is entered on the first day; other signals pay when they change from cash.
        turnover = pos.diff().abs().fillna(abs(pos.iloc[0]))
        net = pos * returns[symbol] - FEE * turnover
        portfolio_series[(symbol, strategy)] = net
        for label, start, end in [('train', '2021-01-01', '2024-01-01'), ('test', '2024-01-01', None)]:
            mask = net.index >= pd.Timestamp(start, tz='UTC')
            if end:
                mask &= net.index < pd.Timestamp(end, tz='UTC')
            sample = net.loc[mask]
            if sample.empty: continue
            equity = (1 + sample).cumprod()
            years = len(sample) / 365.0
            cagr = equity.iloc[-1] ** (1 / years) - 1
            vol = sample.std(ddof=1) * np.sqrt(365)
            sharpe = sample.mean() / sample.std(ddof=1) * np.sqrt(365) if sample.std(ddof=1) else np.nan
            maxdd = (equity / equity.cummax() - 1).min()
            exposure = float(pos.loc[sample.index].mean())
            rows.append({'asset':symbol,'strategy':strategy,'period':label,'start':sample.index.min().date().isoformat(),'end':sample.index.max().date().isoformat(),'days':len(sample),'cagr':cagr,'vol':vol,'sharpe':sharpe,'max_drawdown':maxdd,'exposure':exposure,'turnover_units_per_year':turnover.loc[sample.index].sum()/years})

summary = pd.DataFrame(rows)
summary.to_csv(BASE / 'backtest_summary.csv', index=False)
# Equal-weight portfolios with daily rebalancing of four independent signal sleeves. Include rebalance costs as trade-only position changes per sleeve.
port_rows=[]
for strategy in ['BuyHold','SMA200','Mom90','RSI2_MR']:
    sleeve = pd.concat([portfolio_series[(s,strategy)].rename(s) for s in SYMBOLS], axis=1)
    port = sleeve.mean(axis=1)
    for label, start, end in [('train','2021-01-01','2024-01-01'),('test','2024-01-01',None)]:
        mask=port.index>=pd.Timestamp(start,tz='UTC')
        if end: mask &= port.index<pd.Timestamp(end,tz='UTC')
        sample=port.loc[mask]
        equity=(1+sample).cumprod(); years=len(sample)/365
        vol=sample.std(ddof=1)*np.sqrt(365)
        port_rows.append({'asset':'EW4','strategy':strategy,'period':label,'start':sample.index.min().date().isoformat(),'end':sample.index.max().date().isoformat(),'days':len(sample),'cagr':equity.iloc[-1]**(1/years)-1,'vol':vol,'sharpe':sample.mean()/sample.std(ddof=1)*np.sqrt(365),'max_drawdown':(equity/equity.cummax()-1).min(),'exposure':np.mean([signals[(s,strategy)].mean() for s in SYMBOLS]),'turnover_units_per_year':np.nan})
pd.concat([summary,pd.DataFrame(port_rows)],ignore_index=True).to_csv(BASE/'backtest_summary.csv',index=False)
prices.to_csv(BASE/'prices_aligned.csv')
print(f'data {prices.index.min().date()} to {prices.index.max().date()}, {len(prices)} aligned days')
print(pd.read_csv(BASE/'backtest_summary.csv').query("asset == 'EW4'").to_string(index=False))
