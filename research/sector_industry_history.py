"""Historical analogy for the 75/25 equal-sector portfolio, January 1927 to December 1997."""
from io import BytesIO, StringIO
from zipfile import ZipFile

import numpy as np
import pandas as pd
import requests

from sector_rotation import CACHE, RESULTS, paired_interval, simulate


def french_monthly(name):
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / f"{name}.zip"
    if not path.exists():
        url = f"https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/{name}.zip"
        response = requests.get(url, timeout=45)
        response.raise_for_status()
        path.write_bytes(response.content)
    with ZipFile(BytesIO(path.read_bytes())) as archive:
        lines = archive.read(archive.namelist()[0]).decode("latin1").splitlines()
    header = next(i for i, line in enumerate(lines) if line.startswith(","))
    stop = next(i for i in range(header + 1, len(lines)) if not lines[i][:6].isdigit())
    table = pd.read_csv(StringIO("\n".join(lines[header:stop])), index_col=0)
    table.index = pd.to_datetime(table.index.astype(str), format="%Y%m")
    table = table.loc["1927":"1997"]
    expected = pd.date_range("1927-01-01", "1997-12-01", freq="MS")
    if not table.index.equals(expected) or table.isna().any().any() or (table <= -99.99).any().any():
        raise ValueError(f"Invalid monthly panel in {name}")
    return table / 100


def main():
    industries = french_monthly("12_Industry_Portfolios_CSV")
    factors = french_monthly("F-F_Research_Data_Factors_CSV")
    returns = industries.copy()
    returns.insert(0, "market", factors["Mkt-RF"] + factors["RF"])
    # Synthetic unit prices reconstruct each month's published holding-period return.
    closes = (1 + returns).cumprod()
    opens = closes.shift(1, fill_value=1.)
    result = {}
    for label, share in [("market", 0.), ("equal_industries", .25)]:
        w = pd.DataFrame(share / industries.shape[1], index=returns.index, columns=returns.columns)
        w["market"] = 1 - share
        result[label] = simulate(opens, closes, w, .0005, start="1927-01-01")
    history = pd.DataFrame(result)
    RESULTS.mkdir(exist_ok=True)
    history.to_csv(RESULTS / "industry_history_monthly.csv", index_label="month")
    for a, b in [("1927", "1997"), ("1927", "1961"), ("1962", "1997")]:
        r = history.loc[a:b]
        print(a, b, "CAGR", np.expm1(np.log1p(r).mean() * 12).to_dict())
    print("Annual relative growth interval", paired_interval(
        history.equal_industries, history.market, partial_last=False))


if __name__ == "__main__":
    main()
