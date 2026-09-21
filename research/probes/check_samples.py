"""Offline checks for the specific downloaded samples; not general parsers."""

import json
import re
import sys
from pathlib import Path

import pandas as pd


def main():
    fund_run, market_run = map(Path, sys.argv[1:3])
    vesaf = (fund_run / "vesaf-202608.txt").read_text(encoding="utf-8")
    bcf = (fund_run / "vcbf-bcf-202608.txt").read_text(encoding="utf-8")
    veil = (fund_run / "veil-202608.txt").read_text(encoding="utf-8")
    vesaf_rows = dict((t, float(w)) for t, w in re.findall(r"^([A-Z]{3}) .+ (\d+\.\d+)$", vesaf.split("TOTAL")[0], re.M))
    bcf_section = bcf.split("%/NAV", 1)[1].split("Tổng", 1)[0]
    bcf_rows = dict((t, float(w.replace(",", "."))) for t, w in re.findall(r"([A-Z]{3})\s+(\d+,\d+)", bcf_section))
    # Explicit identity mapping for these ten PDF company names, pending security-master validation.
    names = {"Vingroup": "VIC", "Mobile World": "MWG", "BIDV": "BID", "Vietcombank": "VCB", "VP Bank": "VPB", "Vinhomes": "VHM", "Techcombank": "TCB", "Vietinbank": "CTG", "Hoa Phat Group": "HPG", "Asia Com. Bank": "ACB"}
    veil_rows = {}
    for line in veil.splitlines():
        for name, ticker in names.items():
            if line.startswith(name + " "):
                match = re.search(r" (\d+\.\d+) \$", line)
                if match:
                    veil_rows[ticker] = float(match[1])
    assert (len(vesaf_rows), len(bcf_rows), len(veil_rows)) == (10, 5, 10)
    result = {"scope": "sample checks only; not investment advice", "holdings": {"VESAF": vesaf_rows, "VCBF-BCF": bcf_rows, "VEIL": veil_rows}, "common": sorted(vesaf_rows.keys() & bcf_rows.keys() & veil_rows.keys()), "prices": {}}
    for ticker in ("FPT", "SHS", "ACV"):
        df = pd.read_csv(market_run / f"{ticker}-ohlcv.csv")
        prices = df[["open", "high", "low", "close"]]
        checks = {
            "unique_dates": not df.time.duplicated().any(),
            "sorted_dates": pd.to_datetime(df.time).is_monotonic_increasing,
            "positive_prices": bool((prices > 0).all().all()),
            "nonnegative_volume": bool((df.volume >= 0).all()),
            "ohlc_bounds": bool(((df.low <= prices.min(axis=1)) & (df.high >= prices.max(axis=1))).all()),
            "no_missing_ohlcv": not bool(df[["time", "open", "high", "low", "close", "volume"]].isna().any().any()),
        }
        result["prices"][ticker] = checks
    print(json.dumps(result, ensure_ascii=False, indent=2))
    assert all(all(checks.values()) for checks in result["prices"].values())


if __name__ == "__main__":
    main()
