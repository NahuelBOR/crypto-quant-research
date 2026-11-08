"""Long-only spot replay using cash and units. Never sends exchange orders."""
import pandas as pd

def replay(candles, target, fee=.0015, initial_cash=1., prior_target=0.):
    if fee<0 or fee>=1 or initial_cash<=0: raise ValueError('Invalid cost or capital')
    if not candles.index.equals(target.index): raise ValueError('Indexes must match')
    if target.isna().any() or ((target<0)|(target>1)).any(): raise ValueError('Targets must be between 0 and 1')
    if not 0<=prior_target<=1: raise ValueError('Invalid prior target')
    desired=target.shift(1).fillna(prior_target); cash=float(initial_cash); units=0.; previous=-1.
    ledger=[]; marks=[]
    for t,row in candles.iterrows():
        op=float(row['open']); close=float(row['close']); weight=float(desired.loc[t])
        if op<=0 or close<=0: raise ValueError('Prices must be positive')
        if weight!=previous:
            wealth=cash+units*op
            before_cash,before_units=cash,units
            delta=(weight*wealth/op-units)
            direction=1 if delta>0 else -1
            delta/=1+weight*fee*direction
            cost=abs(delta)*op*fee
            cash-=delta*op+cost; units+=delta
            if cash < -1e-9 or units < -1e-9: raise ArithmeticError('Negative balance')
            if abs(delta)>1e-12:
                ledger.append(dict(time=t,side='buy' if delta>0 else 'sell',price=op,quantity=abs(delta),fee=cost,cash_before=before_cash,cash_after=cash,units_before=before_units,units_after=units,target=weight))
            previous=weight
        marks.append(dict(time=t,cash=cash,units=units,close=close,equity=cash+units*close,target=weight))
    return pd.DataFrame(marks).set_index('time'),pd.DataFrame(ledger)
