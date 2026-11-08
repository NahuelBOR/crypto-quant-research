"""Follow-up hypothesis: confirmation controls churn, weekly sizing controls exposure.
Chosen after inspecting iteration 02; no claim of independent discovery/holdout.
"""
from pathlib import Path
import json
import pandas as pd
import numpy as np
from audit_backtests import simulate,metrics,bootstrap
from iteration_02 import make
ROOT=Path(__file__).resolve().parent; OUT=ROOT/'iteration_03_results'; OUT.mkdir(exist_ok=True)

def candidates(d):
    idx=d.index; base=make(d); r=d.close.pct_change()
    rv=r.rolling(180,min_periods=120).std()*np.sqrt(6*365.25)
    out={}
    for vol in [.30,.45]:
        size=((vol/rv).clip(0,1)*4).round()/4
        size=size.where((idx.weekday==6)&(idx.hour==20)).ffill().fillna(0.)
        out[f'passive_vol{vol}']=size
        for bars in [3,6]:out[f'confirm{bars}_vol{vol}']=base[f'confirmation_{bars}']*size
    out['original_EMA']=base['original_EMA']
    return out

def main():
    (OUT/'plan.json').write_text(json.dumps(dict(reason='Combine two promising mechanisms from iteration02; exploratory post-selection.',parameters=dict(confirmation_bars=[3,6],annual_vol_sizing=[.3,.45]),selection='Highest BTC 2020-22 stress-cost Sharpe among four new combinations. Transfer frozen to ETH.',cost_per_side=[.0015,.003],lag_bars=[1,2]),indent=2))
    frames={}; signals={}
    for asset in ['BTCUSDT','ETHUSDT']:
        d=pd.read_csv(ROOT/f'{asset.lower()}_spot_4h.csv',parse_dates=['open_time']).set_index('open_time')
        d.index=pd.to_datetime(d.index,utc=True); counts=d.groupby(d.index.floor('D')).size()
        stop=counts[counts==6].index[-1]+pd.Timedelta(days=1)
        d=d.loc[d.index<stop];frames[asset]=d;signals[asset]=candidates(d)
        cut=len(d)//2; future=d.copy();future.iloc[cut:,future.columns.get_indexer(['open','high','low','close'])]*=1.5
        other=candidates(future)
        for n in other:assert np.allclose(other[n].iloc[:cut],signals[asset][n].iloc[:cut])
    end=(min(d.index[-1].floor('D') for d in frames.values())+pd.Timedelta(days=1)).strftime('%Y-%m-%d')
    rows=[]; val={}
    for asset,d in frames.items():
        for name,s in signals[asset].items():
            for a,b,p in [('2020-01-01','2023-01-01','train'),('2023-01-01',end,'validation')]+[(f'{y}-01-01',min(f'{y+1}-01-01',end),str(y)) for y in [2023,2024,2025,2026]]:
                for cost,lag,case in [(.0015,1,'base'),(.003,1,'cost_x2'),(.0015,2,'delay_4h')]:
                    r,en,to=simulate(d,s,a,b,cost,lag)
                    rows.append(dict(asset=asset,strategy=name,period=p,case=case,entries=en,total_return=float((1+r).prod()-1),**metrics(r)))
                    if case=='base' and p=='validation':val[(asset,name)]=r
    res=pd.DataFrame(rows)
    ranking=res[(res.asset=='BTCUSDT')&(res.period=='train')&(res.case=='cost_x2')&res.strategy.str.startswith('confirm')].sort_values('Sharpe',ascending=False)
    winner=ranking.iloc[0].strategy; volatility=winner.split('_vol')[1]
    boots=[]
    for a in frames:
        for ref in ['original_EMA','passive_vol'+volatility]:
            boots.append(dict(asset=a,strategy=winner,reference=ref,**bootstrap(val[(a,winner)]-val[(a,ref)])))
    res.to_csv(OUT/'results.csv',index=False);ranking.to_csv(OUT/'training_selection.csv',index=False)
    pd.DataFrame(boots).to_csv(OUT/'bootstrap.csv',index=False)
    pd.DataFrame({a+'_'+n:r for (a,n),r in val.items()}).to_csv(OUT/'daily_returns.csv')
    (OUT/'selection.json').write_text(json.dumps(dict(winner=winner,validation_was_previously_observed=True)))
    print('TRAIN-STRESS WINNER',winner)
    print(ranking.to_string(index=False))
    print(res[(res.strategy.isin([winner,'passive_vol'+volatility,'original_EMA'])) & res.period.isin(['validation','2026'])].to_string(index=False))
    print('YEARLY CHOSEN',res[(res.strategy==winner)&(res.case=='base')].to_string(index=False))
    print(pd.DataFrame(boots).to_string(index=False))
if __name__=='__main__':main()
