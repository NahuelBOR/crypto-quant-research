"""Professional-style crypto ensemble screening: trend, cross-sectional momentum, carry.

Daily marks are derived from the final 8-hour funding observation each UTC day.
Signals calculated at day t are applied from day t+1. The script reports screening
results only; it is not an exchange-grade execution/liquidation simulator.
"""
from pathlib import Path
from itertools import product
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parent
SYMS=['BTCUSDT','ETHUSDT','BNBUSDT','SOLUSDT']
TRAIN_END=pd.Timestamp('2023-01-01',tz='UTC')
FEE_PERP_CASES=[5,10]

def event_frame(sym):
    x=pd.read_csv(ROOT/f'{sym.lower()}_carry_4h.csv',index_col=0,parse_dates=True)
    x.index=pd.to_datetime(x.index,utc=True)
    return x.sort_index()

raw={s:event_frame(s) for s in SYMS}
start=min(x.index.min().floor('D') for x in raw.values())
end=max(x.index.max().floor('D') for x in raw.values())
days=pd.date_range(start,end,freq='D',tz='UTC')
prices={}; perps={}; funding={}; spot_rets={}; perp_rets={}
carry_signal={}
for s,x in raw.items():
    d=x.index.floor('D')
    prices[s]=x.spot.groupby(d).last().reindex(days).ffill()
    perps[s]=x.perp.groupby(d).last().reindex(days).ffill()
    funding[s]=x.funding.groupby(d).sum(min_count=1).reindex(days).fillna(0)
    spot_rets[s]=prices[s].pct_change(fill_method=None).fillna(0)
    perp_rets[s]=perps[s].pct_change(fill_method=None).fillna(0)
    carry_signal[s]={}
    for n in (3,7,14):
        event_mean=x.funding.rolling(n,min_periods=n).mean()
        daily_mean=event_mean.groupby(event_mean.index.floor('D')).last().reindex(days)
        carry_signal[s][n]=daily_mean

px=pd.DataFrame(prices,index=days); ppx=pd.DataFrame(perps,index=days)
spotret=pd.DataFrame(spot_rets,index=days); perp_ret=pd.DataFrame(perp_rets,index=days)
fund=pd.DataFrame(funding,index=days)

def fee_portfolio_returns(target,ret,fund_daily,fee_bps):
    # Signal at close t is executed on the next daily interval.
    w=target.shift(1).fillna(0.)
    turnover=w.diff().abs().sum(axis=1).fillna(w.abs().sum(axis=1))
    pnl=(w*ret).sum(axis=1)-(w*fund_daily).sum(axis=1)-turnover*(fee_bps/1e4)
    return pnl

def stats(r):
    r=r.fillna(0.)
    eq=(1+r).cumprod()
    yrs=len(r)/365.25
    vol=r.std(ddof=1)*np.sqrt(365.25)
    sh=r.mean()/r.std(ddof=1)*np.sqrt(365.25) if r.std(ddof=1)>0 else np.nan
    cg=eq.iloc[-1]**(1/yrs)-1 if yrs>0 and eq.iloc[-1]>0 else -1.
    dd=(eq/eq.cummax()-1).min()
    return dict(CAGR=cg,Sharpe=sh,Vol=vol,MaxDD=dd,total_return=eq.iloc[-1]-1)

def trend_target(lbs,vote_min,mode):
    rets=pd.DataFrame({(s,lb):px[s].pct_change(lb) for s in SYMS for lb in lbs},index=days)
    vol=spotret.rolling(60,min_periods=40).std().shift(1)*np.sqrt(365.25)
    out=pd.DataFrame(0.,index=days,columns=SYMS)
    for t in range(len(days)):
        sig={}
        for s in SYMS:
            votes=np.array([np.sign(rets.loc[days[t],(s,lb)]) if pd.notna(rets.loc[days[t],(s,lb)]) else 0 for lb in lbs])
            n=np.count_nonzero(votes)
            score=votes.sum()
            if n<vote_min or score==0: direction=0
            elif mode=='long_cash': direction=1 if score>0 else 0
            else: direction=np.sign(score)
            sig[s]=direction
        raww={s:(sig[s]/vol.iloc[t][s] if sig[s] and pd.notna(vol.iloc[t][s]) and vol.iloc[t][s]>0 else 0.) for s in SYMS}
        gross=sum(abs(v) for v in raww.values())
        if gross:
            for s in SYMS: out.iloc[t,out.columns.get_loc(s)]=np.clip(raww[s]/gross,-.4,.4)
            # Clipping lowers gross if concentration is high; never lever it back above 1x.
            g=out.iloc[t].abs().sum()
            if g>1: out.iloc[t]/=g
    return out

def cross_target(lookback,k):
    mom=px.pct_change(lookback)
    vol=spotret.rolling(60,min_periods=40).std().shift(1)
    out=pd.DataFrame(0.,index=days,columns=SYMS)
    for i,dt in enumerate(days):
        if dt.weekday()!=0 or i==0: continue
        # Use prior close rank at rebalance; final target is applied with one-day lag below.
        rank=mom.iloc[i].dropna().sort_values()
        if len(rank)<4 or len(rank)<2*k: continue
        shorts=list(rank.index[:k]); longs=list(rank.index[-k:])
        for names,side in ((longs,1),(shorts,-1)):
            inv={s:1/vol.iloc[i][s] for s in names if pd.notna(vol.iloc[i][s]) and vol.iloc[i][s]>0}
            den=sum(inv.values())
            if den:
                for s,v in inv.items(): out.loc[dt,s]=side*.5*v/den
    return out.ffill().fillna(0.)

def carry_sleeve(n,threshold,spot_fee,fut_fee):
    pos=pd.DataFrame(0.,index=days,columns=SYMS)
    # Restrict carry to the two deepest markets in this dataset; BNB/SOL carry was weak/negative in prior screens.
    for s in ('BTCUSDT','ETHUSDT'):
        av=carry_signal[s][n]
        pos[s]=(av>threshold).astype(float).fillna(0.)
    held_raw=pos.shift(1).fillna(0.)
    n_active=held_raw.sum(axis=1).replace(0,np.nan)
    held=held_raw.div(n_active,axis=0).fillna(0.)
    turn=held.diff().abs().sum(axis=1).fillna(held.abs().sum(axis=1))
    # Per account dollar: half spot long and half perpetual short when funding is attractive.
    raw=(held*(spotret-perp_ret+fund)).sum(axis=1)
    return (raw-turn*(spot_fee+fut_fee))/2

# Build and cache sleeve return series across predeclared parameter choices.
trend_specs=[]; trend_rets={}
for lbs in ((20,60,120),(30,90,180),(60,120,240)):
    for vote_min,mode in ((2,'long_short'),(2,'long_cash')):
        name=f'TS_{lbs[0]}_{lbs[1]}_{lbs[2]}_v{vote_min}_{mode}'
        target=trend_target(lbs,vote_min,mode)
        for fee in FEE_PERP_CASES:
            trend_rets[(name,fee)]=fee_portfolio_returns(target,perp_ret,fund,fee)
        trend_specs.append(name)

cross_specs=[]; cross_rets={}
for lb,k in product((30,90,180),(1,)):
    name=f'CS_{lb}_topbottom{k}'
    target=cross_target(lb,k)
    for fee in FEE_PERP_CASES:
        cross_rets[(name,fee)]=fee_portfolio_returns(target,perp_ret,fund,fee)
    cross_specs.append(name)

carry_specs=[]; carry_rets={}
for n,thr in product((3,7,14),(0.,)):
    name=f'Carry_n{n}_thr{thr:g}'
    for spotfee,futfee,label in ((.001,.0005,5),(.002,.001,10)):
        carry_rets[(name,label)]=carry_sleeve(n,thr,spotfee,futfee)
    carry_specs.append(name)

mixes=[(.6,.3,.1),(.5,.3,.2),(.4,.4,.2),(.7,.2,.1),(.5,.2,.3),(.4,.2,.4),(.8,0,.2),(.7,0,.3),(.6,0,.4)]
portfolio_returns={}; meta={}
for ts,cs,ca,mix,fee in product(trend_specs,cross_specs,carry_specs,mixes,FEE_PERP_CASES):
    a,b,c=mix
    name=f'{ts}|{cs}|{ca}|mix={a:.1f},{b:.1f},{c:.1f}|fee{fee}'
    portfolio_returns[name]=a*trend_rets[(ts,fee)]+b*cross_rets[(cs,fee)]+c*carry_rets[(ca,fee)]
    meta[name]=dict(trend=ts,cross=cs,carry=ca,w_trend=a,w_cross=b,w_carry=c,fee_case=fee)

# Add simple baselines and single sleeves for fair context.
for name,r in trend_rets.items(): portfolio_returns[f'{name[0]}|single|fee{name[1]}']=r; meta[f'{name[0]}|single|fee{name[1]}']=dict(trend=name[0],cross='-',carry='-',w_trend=1,w_cross=0,w_carry=0,fee_case=name[1])
for name,r in cross_rets.items(): portfolio_returns[f'{name[0]}|single|fee{name[1]}']=r; meta[f'{name[0]}|single|fee{name[1]}']=dict(trend='-',cross=name[0],carry='-',w_trend=0,w_cross=1,w_carry=0,fee_case=name[1])
for name,r in carry_rets.items(): portfolio_returns[f'{name[0]}|single|fee{name[1]}']=r; meta[f'{name[0]}|single|fee{name[1]}']=dict(trend='-',cross='-',carry=name[0],w_trend=0,w_cross=0,w_carry=1,fee_case=name[1])

# Parameter bagging: average every predeclared model within each sleeve before mixing.
# This reduces dependence on a single winning lookback/threshold.
bag_names=[]
bag_mixes=[(.5,.25,.25),(.6,.2,.2),(.4,.3,.3),(.7,.2,.1),(.8,0,.2),(.6,0,.4)]
for fee in FEE_PERP_CASES:
    tbag=sum(trend_rets[(n,fee)] for n in trend_specs)/len(trend_specs)
    xbag=sum(cross_rets[(n,fee)] for n in cross_specs)/len(cross_specs)
    cb_label=5 if fee==5 else 10
    cbags=[carry_rets[(n,cb_label)] for n in carry_specs]
    cbagg=sum(cbags)/len(cbags)
    portfolio_returns[f'BagTrend|fee{fee}']=tbag; meta[f'BagTrend|fee{fee}']=dict(trend='bagged-all',cross='-',carry='-',w_trend=1,w_cross=0,w_carry=0,fee_case=fee,bagged=True)
    portfolio_returns[f'BagCross|fee{fee}']=xbag; meta[f'BagCross|fee{fee}']=dict(trend='-',cross='bagged-all',carry='-',w_trend=0,w_cross=1,w_carry=0,fee_case=fee,bagged=True)
    portfolio_returns[f'BagCarry|fee{fee}']=cbagg; meta[f'BagCarry|fee{fee}']=dict(trend='-',cross='-',carry='bagged-all',w_trend=0,w_cross=0,w_carry=1,fee_case=fee,bagged=True)
    for a,b,c in bag_mixes:
        name=f'BagSuper_{a:.2f}_{b:.2f}_{c:.2f}|fee{fee}'
        portfolio_returns[name]=a*tbag+b*xbag+c*cbagg
        meta[name]=dict(trend='bagged-all',cross='bagged-all',carry='bagged-all',w_trend=a,w_cross=b,w_carry=c,fee_case=fee,bagged=True)
        bag_names.append(name)

allret=pd.DataFrame(portfolio_returns,index=days)
# Benchmark: equal-weight long-only spot, equal weight BTC/ETH only, and BTC spot.
bench=pd.DataFrame(index=days)
bench['EW4_spot']=spotret.mean(axis=1)
bench['BTC_ETH_spot']=spotret[['BTCUSDT','ETHUSDT']].mean(axis=1)
bench['BTC_spot']=spotret.BTCUSDT

start_eval=pd.Timestamp('2020-01-01',tz='UTC')
end_eval=pd.Timestamp('2026-11-06',tz='UTC')
mask=(days>=start_eval)&(days<end_eval)
evalret=allret.loc[mask]

# Fixed train selection: choose only on 2020-22 Sharpe; report later data separately.
train=evalret.loc[evalret.index<TRAIN_END]
fixed=[]
for name,r in train.items():
    if name not in bag_names or '|fee10' in name: continue
    m=stats(r); fixed.append((name,m['Sharpe'],m['CAGR']))
fixed.sort(key=lambda x: (x[1] if np.isfinite(x[1]) else -9),reverse=True)
chosen=fixed[0][0]
mix_count=len(trend_specs)*len(cross_specs)*len(carry_specs)*len(mixes)
print('Candidates:',len(portfolio_returns),f'({mix_count} fixed-weight ensembles per fee case, plus sleeves).')
print('Fixed bagged SUPER selected only on 2020-22 Sharpe:',chosen)

rows=[]
periods=[('train_2020_22','2020-01-01','2023-01-01'),('validation_2023_26','2023-01-01',None),('2023','2023-01-01','2024-01-01'),('2024_25','2024-01-01','2026-01-01'),('2026_ytd','2026-01-01',None)]
for name,r in allret.items():
    if name not in meta: continue
    for label,a,b in periods:
        xx=r.loc[r.index>=pd.Timestamp(a,tz='UTC')]
        if b: xx=xx.loc[xx.index<pd.Timestamp(b,tz='UTC')]
        m=stats(xx)
        rows.append(dict(name=name,period=label,**meta[name],**m))
for name,r in bench.items():
    for label,a,b in periods:
        xx=r.loc[r.index>=pd.Timestamp(a,tz='UTC')]
        if b:xx=xx.loc[xx.index<pd.Timestamp(b,tz='UTC')]
        rows.append(dict(name=name,period=label,trend='-',cross='-',carry='-',w_trend=0,w_cross=0,w_carry=0,fee_case=0,**stats(xx)))
summary=pd.DataFrame(rows); summary.to_csv(ROOT/'ensemble_quant_summary.csv',index=False)

# Annual walk-forward: each Jan select the best 3y training Sharpe among base-cost candidates.
# The strategy is frozen for the next calendar year; no parameters are chosen using that year.
wf=[]; wf_daily=pd.Series(index=days,dtype=float); selections=[]
base_names=[n for n in allret.columns if '|fee5' in n]
for year in range(2023,2027):
    cutoff=pd.Timestamp(f'{year}-01-01',tz='UTC')
    tr_start=cutoff-pd.Timedelta(days=365*3)
    trmask=(days>=tr_start)&(days<cutoff)
    scores=[]
    for n in base_names:
        x=allret.loc[trmask,n]
        if len(x)<500: continue
        m=stats(x); scores.append((n,m['Sharpe']))
    scores.sort(key=lambda x:(x[1] if np.isfinite(x[1]) else -9),reverse=True)
    if not scores:continue
    winner=scores[0][0]
    end_year=pd.Timestamp(f'{year+1}-01-01',tz='UTC')
    testmask=(days>=cutoff)&(days<end_year)
    wf_daily.loc[days[testmask]]=allret.loc[days[testmask],winner].to_numpy()
    selections.append(dict(year=year,chosen=winner,train_sharpe=scores[0][1],train_start=tr_start.date().isoformat(),train_end=(cutoff-pd.Timedelta(days=1)).date().isoformat()))
    wf.append((year,winner,stats(allret.loc[testmask,winner])))
wf_daily=wf_daily.dropna(); wf_daily.to_csv(ROOT/'ensemble_quant_walkforward_daily.csv',header=['return'])
pd.DataFrame(selections).to_csv(ROOT/'ensemble_quant_walkforward_selections.csv',index=False)
walk=stats(wf_daily); pd.DataFrame([walk]).to_csv(ROOT/'ensemble_quant_walkforward_summary.csv',index=False)

print('\nTrain-selected fixed portfolio validation and annual slices:')
print(summary[(summary.name==chosen)][['name','period','CAGR','Sharpe','Vol','MaxDD','total_return']].to_string(index=False))
print('\nTop validation portfolios (diagnostic only, selected after seeing validation):')
print(summary[(summary.period=='validation_2023_26')&(summary.fee_case==5)&(summary.w_carry>0)&(summary.w_cross>0)&(summary.w_trend>0)].sort_values('Sharpe',ascending=False).head(10)[['name','CAGR','Sharpe','Vol','MaxDD','total_return']].to_string(index=False))
print('\nBenchmarks validation:')
print(summary[(summary.period=='validation_2023_26')&summary.name.isin(bench.columns)][['name','CAGR','Sharpe','Vol','MaxDD','total_return']].to_string(index=False))
print('\nWalk-forward selections (3y train, next calendar year):')
print(pd.DataFrame(selections).to_string(index=False))
print('Walk-forward aggregate 2023-2026:',walk)

# Separate low-dimensional walk-forward over the four parameter-bagged super mixes.
wf_bag=pd.Series(index=days,dtype=float); sel_bag=[]
base_bags=[n for n in bag_names if '|fee5' in n]
for year in range(2023,2027):
    cutoff=pd.Timestamp(f'{year}-01-01',tz='UTC'); tr_start=cutoff-pd.Timedelta(days=365*3)
    tm=(days>=tr_start)&(days<cutoff); candidates=[]
    for n in base_bags:
        mm=stats(allret.loc[tm,n]); candidates.append((n,mm['Sharpe']))
    candidates.sort(key=lambda q:(q[1] if np.isfinite(q[1]) else -9),reverse=True)
    win=candidates[0][0]; em=pd.Timestamp(f'{year+1}-01-01',tz='UTC'); vm=(days>=cutoff)&(days<em)
    wf_bag.loc[days[vm]]=allret.loc[days[vm],win].to_numpy()
    sel_bag.append(dict(year=year,chosen=win,train_sharpe=candidates[0][1],train_start=tr_start.date().isoformat(),train_end=(cutoff-pd.Timedelta(days=1)).date().isoformat()))
wf_bag=wf_bag.dropna(); bagwalk=stats(wf_bag)
pd.DataFrame(sel_bag).to_csv(ROOT/'ensemble_quant_bag_walkforward_selections.csv',index=False)
pd.DataFrame([bagwalk]).to_csv(ROOT/'ensemble_quant_bag_walkforward_summary.csv',index=False)
print('\nFixed parameter-bagged super mixes (train/validation):')
print(summary[summary.name.isin(bag_names)&summary.period.isin(['train_2020_22','validation_2023_26','2023','2024_25','2026_ytd'])][['name','period','CAGR','Sharpe','Vol','MaxDD','total_return']].to_string(index=False))
print('\nParameter-bagged walk-forward selections:')
print(pd.DataFrame(sel_bag).to_string(index=False))
print('Parameter-bagged walk-forward aggregate:',bagwalk)
