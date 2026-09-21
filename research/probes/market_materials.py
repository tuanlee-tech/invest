"""Small guest-access probe for vnstock==4.0.8; no API key registration."""

import json
import os
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path

# Prevent the dependency's optional agent bootstrap from editing instruction files.
os.environ["VNSTOCK_DISABLE_AGENT_SETUP"] = "1"
os.environ["VNSTOCK_DISABLE_GLOBAL_AGENT"] = "1"

from vnstock import Fundamental, Market


def main():
    output = Path(__file__).resolve().parent / "runs" / datetime.now(timezone.utc).strftime("market-%Y%m%dT%H%M%S%fZ")
    output.mkdir(parents=True, exist_ok=False)
    market, fundamental = Market(), Fundamental()
    tasks = [(f"{ticker}-ohlcv", lambda t=ticker: market.equity(t).ohlcv(start="2025-09-01", end="2026-09-18", count=400)) for ticker in ("FPT", "SHS", "ACV")]
    tasks += [
        ("FPT-income", lambda: fundamental.equity("FPT").income_statement(period="year")),
        ("FPT-ratio", lambda: fundamental.equity("FPT").ratio()),
    ]
    results = []
    for name, fetch in tasks:
        row = {"id": name, "vnstock": version("vnstock"), "retrieved_at": datetime.now(timezone.utc).isoformat()}
        try:
            df = fetch()
            row.update(rows=len(df), columns=[str(c) for c in df.columns], attrs={str(k): str(v) for k, v in df.attrs.items()})
            df.to_csv(output / f"{name}.csv", index=True)
            row["nonempty"] = not df.empty
            if "time" in df.columns:
                row.update(first_time=str(df["time"].min()), last_time=str(df["time"].max()))
        except Exception as exc:
            row["error"] = f"{type(exc).__name__}: {exc}"
        results.append(row)
        (output / "results.json").write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
        print(json.dumps(row, ensure_ascii=True), flush=True)
    print(f"Evidence directory: {output}")


if __name__ == "__main__":
    main()
