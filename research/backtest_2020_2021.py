"""Replay the frozen BTC/ETH rule over 2020–2021 using cached spot candles."""
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))
from quantbot.data import validate
from quantbot.strategy import targets
from audit_backtests import metrics, simulate

START = "2020-01-01"
END = "2022-01-01"
SYMBOLS = ("BTCUSDT", "ETHUSDT")
SCENARIOS = (
    ("strategy", 0.0015, 1, 1.0, False),
    ("strategy_double_cost", 0.003, 1, 1.0, False),
    ("strategy_double_cost_delay_4h", 0.003, 2, 1.0, False),
    ("buy_hold", 0.0015, 1, 1.0, False),
    ("half_crypto_half_cash", 0.0015, 1, 0.5, True),
    ("quarter_crypto_three_quarters_cash", 0.0015, 1, 0.25, True),
)


def main():
    daily = {}
    for symbol in SYMBOLS:
        name = symbol.lower()
        warmup = ROOT / "backtest_2018_2019_results" / f"{name}_spot_4h_2017_2019.csv"
        historical = ROOT / f"{name}_spot_4h.csv"
        frames = [
            pd.read_csv(path, index_col="open_time", parse_dates=["open_time"])[
                ["open", "high", "low", "close", "volume"]
            ]
            for path in (warmup, historical)
        ]
        candles = pd.concat(frames).loc[: "2021-12-31"]
        validate(candles)
        test = candles.loc[START:]
        expected = pd.date_range(START, END, tz="UTC", freq="4h", inclusive="left")
        gaps = expected.difference(test.index)
        if len(test.index.floor("D").unique()) != 731:
            raise ValueError(f"At least one full day is absent for {symbol}")
        print(f"{symbol}: {len(test)} candles, missing opens: {gaps.tolist()}")

        signal = targets(candles)
        passive = pd.Series(1.0, index=candles.index)
        for label, cost, lag, allocation, rebalance in SCENARIOS:
            source = signal if label.startswith("strategy") else passive
            r, _, _ = simulate(
                candles, source, START, END, cost=cost, lag=lag,
                allocation=allocation, rebalance=rebalance,
            )
            daily[(symbol, label)] = r

    for label, *_ in SCENARIOS:
        # Equal capital at inception only. The sleeves keep their own cash and units.
        equity = pd.concat(
            [(1 + daily[(symbol, label)]).cumprod() for symbol in SYMBOLS], axis=1
        ).mean(axis=1)
        r = equity.pct_change()
        r.iloc[0] = equity.iloc[0] - 1
        daily[("portfolio", label)] = r

    rows = []
    for (asset, label), r in daily.items():
        for period, sample in [("2020-2021", r), ("2020", r[r.index.year == 2020]),
                               ("2021", r[r.index.year == 2021])]:
            rows.append({"asset": asset, "scenario": label, "period": period,
                         "total_return": (1 + sample).prod() - 1, **metrics(sample)})
    output = ROOT / "backtest_2020_2021_results"
    output.mkdir(exist_ok=True)
    result = pd.DataFrame(rows)
    result.to_csv(output / "results.csv", index=False)
    pd.DataFrame({f"{a}_{s}": r for (a, s), r in daily.items()}).to_csv(output / "daily_returns.csv")
    print(result[result.asset.eq("portfolio")].to_string(index=False))


if __name__ == "__main__":
    main()
