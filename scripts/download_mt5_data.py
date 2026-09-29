from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from app.data.mt5_market_data import MT5MarketDataProvider
from app.data.validation import validate_market_frame


def parse_dt(value: str) -> datetime:
    dt = pd.Timestamp(value)
    if dt.tzinfo is None:
        dt = dt.tz_localize("UTC")
    else:
        dt = dt.tz_convert("UTC")
    return dt.to_pydatetime()


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Download historical OHLC data from MetaTrader 5")
    p.add_argument("--symbol", required=True)
    p.add_argument("--timeframe", required=True, choices=sorted(MT5MarketDataProvider.TF_MAP))
    p.add_argument("--start", required=True, help="ISO datetime/date, interpreted as UTC when no timezone is supplied")
    p.add_argument("--end", required=True)
    p.add_argument("--output", required=True)
    return p


def main() -> int:
    args = build_parser().parse_args()
    start, end = parse_dt(args.start), parse_dt(args.end)
    try:
        import MetaTrader5 as mt5
    except ImportError as exc:
        raise SystemExit("MetaTrader5 is not installed. Install the MT5 optional dependency on supported Windows environments.") from exc

    if not mt5.initialize():
        raise SystemExit(f"MT5 initialize failed: {mt5.last_error()}")
    try:
        provider = MT5MarketDataProvider(mt5)
        df = provider.get_candles_range(args.symbol, args.timeframe, start, end)
        errors = validate_market_frame(df)
        if errors:
            raise SystemExit("Invalid downloaded data:\n- " + "\n- ".join(errors))
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        export = df.reset_index().rename(columns={"timestamp": "timestamp"})
        export.to_csv(output, index=False)
        print(f"Downloaded {len(df)} candles: {args.symbol} {args.timeframe}")
        print(f"Range: {df.index.min()} -> {df.index.max()}")
        print(f"Output: {output}")
        return 0
    finally:
        mt5.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
