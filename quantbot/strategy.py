"""Frozen candidate signals, evaluated only on complete 4-hour candles."""
import numpy as np
import pandas as pd

def targets(d):
    if not d.index.is_monotonic_increasing or d.index.has_duplicates:
        raise ValueError('Candles must be ordered and unique')
    c=d['close']; idx=d.index
    e20=c.ewm(span=20,adjust=False).mean(); e100=c.ewm(span=100,adjust=False).mean()
    base=(e20>e100)&(c>c.rolling(200).mean())
    entry=(base.rolling(3).min()==1).fillna(False)
    exit_=(~base).rolling(3).min().eq(1).fillna(False)
    state=False; states=[]
    for a,b in zip(entry,exit_):
        if state and b: state=False
        elif not state and a: state=True
        states.append(float(state))
    trend=pd.Series(states,index=idx)
    vol=c.pct_change().rolling(180,min_periods=120).std()*np.sqrt(6*365.25)
    size=((.30/vol).clip(0,1)*4).round()/4
    sizing=size.where((idx.weekday==6)&(idx.hour==20)).ffill().fillna(0.)
    return (trend*sizing).rename('target')
