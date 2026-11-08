"""Validation only: gaps are reported and prices are never synthesized."""
import pandas as pd

def validate(d):
    required={'open','high','low','close','volume'}
    if not required.issubset(d.columns): raise ValueError('Missing OHLCV columns')
    if not isinstance(d.index,pd.DatetimeIndex) or d.index.tz is None: raise ValueError('Timezone-aware index required')
    if not d.index.is_monotonic_increasing or d.index.has_duplicates: raise ValueError('Timestamps must be sorted and unique')
    if d[list(required)].isna().any().any(): raise ValueError('Missing OHLCV values')
    if (d[['open','high','low','close']]<=0).any().any() or (d.volume<0).any(): raise ValueError('Invalid prices or volume')
    if ((d.low>d[['open','close']].min(axis=1))|(d.high<d[['open','close']].max(axis=1))|(d.low>d.high)).any(): raise ValueError('Inconsistent OHLC')
    diffs=d.index.to_series().diff().dropna()
    return diffs[diffs!=pd.Timedelta(hours=4)]
