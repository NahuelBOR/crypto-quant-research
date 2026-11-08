"""Frozen hypothesis batch after the audit. Spot only; executable target signals.
Run python iteration_02.py. This is retrospective research, not an untouched holdout.
"""
from pathlib import Path
import json, hashlib
import numpy as np
import pandas as pd
from audit_backtests import signal, simulate, metrics, bootstrap, checks

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'iteration_02_results'
OUT.mkdir(exist_ok=True)

def state(entry,exit):
    on=False; a=[]
    for en,ex in zip(entry.fillna(False),exit.fillna(False)):
        if on and ex: on=False
        elif not on and en: on=True
        a.append(float(on))
    return pd.Series(a,index=entry.index)

def make(d):
    c=d.close; idx=d.index
    e20=c.ewm(span=20,adjust=False).mean(); e100=c.ewm(span=100,adjust=False).mean()
    ma=c.rolling(200).mean(); base=(e20>e100)&(c>ma)
    tr=pd.concat([d.high-d.low,(d.high-c.shift()).abs(),(d.low-c.shift()).abs()],axis=1).max(axis=1)
    atr=tr.ewm(alpha=1/42,adjust=False,min_periods=42).mean()
    out={'original_EMA':base.astype(float)}
    for b in [.005,.01]:
        out[f'hysteresis_{b}']=state((e20>e100*(1+b))&(c>ma*(1+b)),(e20<e100*(1-b))|(c<ma*(1-b)))
    for bars in [3,6]:
        out[f'confirmation_{bars}']=state(base.rolling(bars).min()==1,(~base).rolling(bars).min()==1)
    for n in [120,240]:
        out[f'channel_{n}']=state(c>d.high.rolling(n).max().shift(),c<d.low.rolling(n//2).min().shift())
    for mult in [3.,5.]:
        ent=(c>d.high.rolling(120).max().shift()).to_numpy(); aa=atr.to_numpy(); cc=c.to_numpy()
        on=False; peak=0.; vals=[]
        for i in range(len(c)):
            if on:
                peak=max(peak,cc[i])
                if cc[i]<peak-mult*aa[i]: on=False
            elif ent[i] and np.isfinite(aa[i]): on=True; peak=cc[i]
            vals.append(float(on))
        out[f'breakout_trail_{mult}']=pd.Series(vals,index=idx)
    # Independent trend horizons vote on fractional exposure; no retroactive daily signal.
    votes=pd.concat([(c.ewm(span=f,adjust=False).mean()>c.ewm(span=s,adjust=False).mean()).astype(float) for f,s in [(20,100),(60,300),(120,600)]],axis=1)
    ladder=votes.mean(axis=1)
    for cadence in ['daily','weekly']:
        update=(idx.hour==20)&((idx.weekday==6) if cadence=='weekly' else True)
        out[f'ladder_{cadence}']=ladder.where(update).ffill().fillna(0.)
    # Coarse sizing prevents high turnover from tiny volatility changes.
    rv=c.pct_change().rolling(180,min_periods=120).std()*np.sqrt(6*365.25)
    for target in [.30,.45]:
        sizing=(target/rv).clip(0,1)
        sizing=(sizing*4).round()/4
        held=sizing.where((idx.weekday==6)&(idx.hour==20)).ffill().fillna(0.)
        out[f'volgate_{target}']=held*base
    slow=c.ewm(span=240,adjust=False).mean(); medium=c.ewm(span=60,adjust=False).mean()
    for k in [1.,2.]:
        out[f'pullback_{k}']=state((medium>slow)&(c<e20-k*atr),(c>e20)|(medium<slow))
    # Path-dependent cooldown following a trend exit: require a fresh local high to reenter.
    for n in [12,30]:
        ent=base&(c>d.high.rolling(n).max().shift())
        out[f'reentry_{n}']=state(ent,~base)
    return {k:v.astype(float).fillna(0.) for k,v in out.items()}

def family(n): return n.rsplit('_',1)[0]

def ranking(d,sigs,a,b):
    scores=[]
    for n,s in sigs.items():
        r,_,_=simulate(d,s,a,b,cost=.003)
        m=metrics(r)
        scores.append(dict(name=n,score=m['Sharpe'] if m['CAGR']>0 and m['MaxDD']>-.5 else -100.,**m))
    return sorted(scores,key=lambda q:q['score'],reverse=True)

def main():
    checks()
    frames={}; sigs={}; hashes={}
    for sym in ['BTCUSDT','ETHUSDT']:
        p=ROOT/f'{sym.lower()}_spot_4h.csv'; hashes[sym]=hashlib.sha256(p.read_bytes()).hexdigest()
        d=pd.read_csv(p,parse_dates=['open_time']).set_index('open_time').sort_index()
        d.index=pd.to_datetime(d.index,utc=True)
        counts=d.groupby(d.index.floor('D')).size(); stop=counts[counts==6].index[-1]+pd.Timedelta(days=1)
        d=d.loc[d.index<stop]; frames[sym]=d; sigs[sym]=make(d)
        for frac in [.45,.7]:
            cut=int(len(d)*frac); amended=d.copy()
            amended.iloc[cut:,amended.columns.get_indexer(['open','high','low','close'])]*=1.5
            altered=make(amended)
            for name in sigs[sym]:
                assert np.allclose(sigs[sym][name].iloc[:cut],altered[name].iloc[:cut]),name
    end=(min(d.index[-1].floor('D') for d in frames.values())+pd.Timedelta(days=1)).strftime('%Y-%m-%d')
    plan=dict(hypotheses=list(sigs['BTCUSDT']),count=len(sigs['BTCUSDT']),end_exclusive=end,hashes=hashes,
              selection='Training stress-cost Sharpe, positive CAGR, max drawdown above -50%; three-year trailing annual selection of top 3 distinct families.',
              fill='Next 4h open; 15bp total cost per side, stress30bp; long spot <=100%; cash zero return.',
              warning='Design uses previously inspected history. No true new holdout. No extra parameter tuning after batch results.')
    (OUT/'plan.json').write_text(json.dumps(plan,indent=2))
    d=frames['BTCUSDT']; ss=sigs['BTCUSDT']
    ranks=ranking(d,ss,'2020-01-01','2023-01-01')
    pd.DataFrame(ranks).to_csv(OUT/'training_ranking.csv',index=False)
    winner=ranks[0]['name']; print('TRAIN CHOICE',winner,flush=True)
    rows=[]; valret={}; picked=[]
    for sym in frames:
        for n,s in sigs[sym].items():
            for a,b,p in [('2023-01-01',end,'validation'),('2026-01-01',end,'2026')]:
                for cost,lag,case in [(.0015,1,'base'),(.003,1,'cost_x2'),(.0015,2,'delay_4h')]:
                    r,en,to=simulate(frames[sym],s,a,b,cost,lag)
                    rows.append(dict(asset=sym,strategy=n,period=p,case=case,entries=en,**metrics(r)))
                    if sym=='BTCUSDT' and p=='validation' and case=='base':valret[n]=r
    # Combine TARGETS before execution. Fees apply to changes in actual net quantities.
    rawwf=pd.Series(0.,index=d.index)
    for year in range(2023,2027):
        rank=ranking(d,ss,f'{year-3}-01-01',f'{year}-01-01')
        names=[]; fam=set()
        for item in rank:
            if item['score']<=-100:continue
            if family(item['name']) not in fam:
                names.append(item['name']); fam.add(family(item['name']))
            if len(names)==3:break
        mask=(d.index>=pd.Timestamp(f'{year}-01-01',tz='UTC'))&(d.index<pd.Timestamp(f'{year+1}-01-01',tz='UTC'))
        if names: rawwf.loc[mask]=sum(ss[n] for n in names).loc[mask]/len(names)
        picked.append(dict(year=year,models=';'.join(names)))
    for cost,lag,case in [(.0015,1,'base'),(.003,1,'cost_x2'),(.0015,2,'delay_4h')]:
        r,en,to=simulate(d,rawwf,'2023-01-01',end,cost,lag)
        rows.append(dict(asset='BTCUSDT',strategy='walkforward_top3',period='validation',case=case,entries=en,**metrics(r)))
        if case=='base':valret['walkforward_top3']=r
    for n,weight in [('passive_BTC',1.),('BTC60_cash40',.6)]:
        r,en,to=simulate(d,pd.Series(1.,index=d.index),'2023-01-01',end,allocation=weight,rebalance=weight<1)
        valret[n]=r; rows.append(dict(asset='BTCUSDT',strategy=n,period='validation',case='base',entries=en,**metrics(r)))
    # Quantify uncertainty against BOTH the earlier candidate and a simple risk-reduced benchmark.
    boot=[]
    for n in [winner,'walkforward_top3']:
        for ref in ['original_EMA','BTC60_cash40']:
            boot.append(dict(strategy=n,reference=ref,**bootstrap(valret[n]-valret[ref])))
    pd.DataFrame(rows).to_csv(OUT/'results.csv',index=False)
    pd.DataFrame(picked).to_csv(OUT/'walkforward_choices.csv',index=False)
    pd.DataFrame(valret).to_csv(OUT/'daily_returns.csv')
    pd.DataFrame(boot).to_csv(OUT/'bootstrap.csv',index=False)
    print('SELECTED AND REFERENCES')
    print(pd.DataFrame(rows).query("strategy in @winner or strategy in ['walkforward_top3','original_EMA','BTC60_cash40','passive_BTC']").to_string(index=False))
    print('EXPLORATORY VALIDATION RANKING (NOT A SELECTION RULE)')
    print(pd.DataFrame(rows).query("asset=='BTCUSDT' and period=='validation' and case=='base'").sort_values('Sharpe',ascending=False).head(8).to_string(index=False))
    print(pd.DataFrame(boot).to_string(index=False));print(picked)

if __name__=='__main__':main()
