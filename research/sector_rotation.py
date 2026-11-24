"""Monthly SPY core with a relative-momentum sector sleeve. Offline with cached data."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd
import requests

from backtest_spy import metrics


ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "research" / "sector_rotation_results"
CACHE = ROOT / "replay_output" / "sector_prices"
SECTORS = ["XLB", "XLE", "XLF", "XLI", "XLK", "XLP", "XLU", "XLV", "XLY"]
ASSETS = ["SPY", *SECTORS]
START = "2000-02-01"
END = "2026-11-13"


def prices(symbol, end):
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / f"{symbol}_{end}.csv"
    if path.exists():
        return pd.read_csv(path, index_col="date", parse_dates=True)
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
    cutoff = pd.Timestamp(end, tz="UTC") + pd.Timedelta(days=1)
    response = requests.get(url, params=dict(period1=897000000, period2=int(cutoff.timestamp()),
                            interval="1d", events="div,splits"), timeout=45,
                            headers={"User-Agent": "Mozilla/5.0"})
    response.raise_for_status()
    raw = response.json()["chart"]["result"][0]
    idx = pd.to_datetime(raw["timestamp"], unit="s", utc=True).tz_convert("America/New_York")
    idx = idx.tz_localize(None).normalize().rename("date")
    quote = pd.DataFrame(raw["indicators"]["quote"][0], index=idx)
    adj = pd.Series(raw["indicators"]["adjclose"][0]["adjclose"], index=idx)
    frame = pd.DataFrame({"open": quote.open * adj / quote.close, "close": adj})
    if not idx.is_unique or not idx.is_monotonic_increasing:
        raise ValueError(f"{symbol}: duplicate or unordered dates")
    frame.to_csv(path)
    return frame


def load_panel(end):
    with ThreadPoolExecutor(max_workers=4) as pool:
        frames = dict(zip(ASSETS, pool.map(lambda ticker: prices(ticker, end), ASSETS)))
    sessions = frames["SPY"].loc["1998-12-22":end].index
    for symbol, frame in frames.items():
        if not frame.loc[sessions[0]:end].index.equals(sessions):
            raise ValueError(f"{symbol}: dates differ from SPY")
    panel = pd.concat(frames, axis=1).loc[sessions]
    if not np.isfinite(panel).all().all() or (panel <= 0).any().any():
        raise ValueError("Missing or nonpositive adjusted prices")
    return panel.xs("open", axis=1, level=1), panel.xs("close", axis=1, level=1)


def targets(closes, mode="rotation"):
    # A row is indexed by execution day. Only completed prior months enter the ranking.
    months = closes.index.to_period("M")
    monthly = closes.groupby(months).last()
    rel = np.log(monthly[SECTORS]).sub(np.log(monthly.SPY), axis=0)
    # At March's first open the February signal measures returns ending in January.
    short = rel.diff(6).shift(2)
    long = rel.diff(12).shift(2)
    moving_average = monthly.rolling(10).mean()
    above = (monthly > moving_average).shift(1)
    first = closes.index[~months.duplicated()]
    weights = pd.DataFrame(0., index=first, columns=ASSETS)
    for day in first:
        month = day.to_period("M")
        if mode in ("breadth", "trend_only"):
            weak_market = not above.loc[month, "SPY"]
            few_leaders = above.loc[month, SECTORS].sum() <= 3
            defensive = weak_market and (few_leaders or mode == "trend_only")
            weights.loc[day, "SPY"] = .5 if defensive else 1.
            continue
        if mode == "rotation":
            a, b = short.loc[month], long.loc[month]
            score = (a + b) / 2
            leaders = score[(a > 0) & (b > 0)].sort_values(ascending=False, kind="stable").head(3)
            weights.loc[day, leaders.index] = .25 / 3
        elif mode == "equal_sectors":
            weights.loc[day, SECTORS] = .25 / len(SECTORS)
        elif mode == "fixed_tech":
            weights.loc[day, "XLK"] = .25
        elif mode != "spy":
            raise ValueError(mode)
        weights.loc[day, "SPY"] = 1 - weights.loc[day, SECTORS].sum()
    return weights


def simulate(opens, closes, schedule, fee, start=START):
    opens, closes = opens.loc[start:], closes.loc[start:]
    if opens.index[0] not in schedule.index:
        raise ValueError("Initial allocation required on first day")
    weights = schedule.reindex(opens.index)
    units = np.zeros(opens.shape[1])
    cash = 1.
    equity = 1.
    history = []
    for op, cl, w in zip(opens.to_numpy(), closes.to_numpy(), weights.to_numpy()):
        if np.isfinite(w[0]):
            holding = units * op
            before = holding.sum() + cash
            after = before
            # Invest the remaining NAV after charging each traded dollar on each leg.
            for _ in range(8):
                after = before - fee * np.abs(after * w - holding).sum()
            units = after * w / op
            cash = after * (1 - w.sum())
        at_close = units @ cl + cash
        history.append(at_close / equity - 1)
        equity = at_close
    history[-1] -= (1 + history[-1]) * fee * (1 - cash / equity)
    return pd.Series(history, index=opens.index)


def paired_interval(portfolio, market, block=6, partial_last=True):
    # Monthly relative log returns. Resample paired circular blocks with replacement.
    active = (np.log1p(portfolio) - np.log1p(market)).groupby(portfolio.index.to_period("M")).sum()
    if partial_last:
        active = active.iloc[:-1]
    rng = np.random.default_rng(7119)
    n = len(active)
    starts = rng.integers(n, size=(5000, int(np.ceil(n / block))))
    index = ((starts[:, :, None] + np.arange(block)) % n).reshape(len(starts), -1)[:, :n]
    samples = np.expm1(active.to_numpy()[index].mean(axis=1) * 12)
    return np.quantile(samples, [.025, .975])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--signal", metavar="YYYY-MM-DD",
                        help="Print targets for a historical session at its open (data fetched through date)")
    parser.add_argument("--rule", choices=["equal_sectors", "rotation", "breadth"], default="equal_sectors",
                        help="Monthly paper signal to display with --signal")
    args = parser.parse_args()
    end = args.signal or END
    opens, closes = load_panel(end)
    if args.signal:
        date = pd.Timestamp(args.signal)
        if date not in closes.index or date < pd.Timestamp(START):
            parser.error("Choose a completed trading session within the test history")
        schedule = targets(closes, args.rule)
        if date in schedule.index:
            w = schedule.loc[date].copy()
            w.loc["cash"] = 1 - w.sum()
            print(w.to_string())
        else:
            print("Hold existing positions until the first trading session of the next month.")
        return
    if str(opens.index[-1].date()) != END:
        raise ValueError("Price history ends before the fixed cutoff")
    RESULTS.mkdir(exist_ok=True)
    runs = {}
    schedule = targets(closes).loc[START:]
    schedule.to_csv(RESULTS / "target_weights.csv", index_label="execution_date")
    breadth = targets(closes, "breadth").loc[START:]
    breadth.SPY.to_csv(RESULTS / "breadth_spy_weights.csv", index_label="execution_date")
    for mode in ["rotation", "spy", "equal_sectors", "fixed_tech", "breadth", "trend_only"]:
        weights = targets(closes, mode)
        runs[mode] = simulate(opens, closes, weights, .0005)
    buy_once = targets(closes, "equal_sectors").loc[START:].iloc[:1]
    runs["equal_sectors_buy_once"] = simulate(opens, closes, buy_once, .0005)
    for bp in [15, 30]:
        for mode in ["rotation", "breadth", "equal_sectors", "spy"]:
            runs[f"{mode}_{bp}bp"] = simulate(opens, closes, targets(closes, mode), bp / 10000)
    delayed = schedule.reindex(opens.loc[START:].index).shift().dropna()
    # Enter SPY on the common start, then delay the sector trades by one session.
    delayed.loc[schedule.index[0]] = [1.] + [0.] * len(SECTORS)
    runs["rotation_delayed"] = simulate(opens, closes, delayed.sort_index(), .0005)
    delayed = breadth.reindex(opens.loc[START:].index).shift().dropna()
    delayed.loc[breadth.index[0]] = [1.] + [0.] * len(SECTORS)
    runs["breadth_delayed"] = simulate(opens, closes, delayed.sort_index(), .0005)
    daily = pd.DataFrame(runs)
    daily.to_csv(RESULTS / "daily_returns.csv", index_label="date", float_format="%.10g")
    rows = []
    for label, period in [("all", daily), ("early", daily.loc[:"2015"]),
                          ("late", daily.loc["2016":])]:
        for mode, r in period.items():
            market = period["spy_" + mode.split("_")[-1]] if mode.endswith("bp") else period.spy
            result = metrics(r)
            result["excess_cagr_pp"] = (result["CAGR"] - metrics(market)["CAGR"]) * 100
            rows.append(dict(period=label, strategy=mode, **result))
    summary = pd.DataFrame(rows)
    summary.to_csv(RESULTS / "summary.csv", index=False)
    annual = daily.groupby(daily.index.year).agg(lambda r: np.expm1(np.log1p(r).sum()))
    annual.to_csv(RESULTS / "annual_returns.csv", index_label="year")
    print(summary.to_string(index=False))
    for mode in ("rotation", "breadth", "equal_sectors", "fixed_tech", "trend_only"):
        for block in (3, 6, 12):
            print(mode, "relative annual growth, 95% interval, block months", block,
                  paired_interval(daily[mode], daily.spy, block))
        print(mode, "full calendar years ahead:",
              (annual[mode].iloc[1:-1] > annual.spy.iloc[1:-1]).sum(), "/", len(annual) - 2)


if __name__ == "__main__":
    main()
