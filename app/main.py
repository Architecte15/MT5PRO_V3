from __future__ import annotations

import argparse
from pathlib import Path
from dataclasses import replace

import pandas as pd

from app.backtest.engine import BacktestEngine
from app.backtest.report import make_equity_curve, make_funnel_chart
from app.config.settings import load_settings, validate_live_config
from app.execution.mock_broker import MockBroker
from app.execution.paper_broker import PaperBroker
from app.execution.mt5_broker import MT5Broker
from app.logging.logger import event, setup_logging
from app.strategy.signal_engine import SignalEngine


def build_parser():
    p = argparse.ArgumentParser(description="Professional Python trading engine")
    p.add_argument("--mode", choices=["demo", "paper", "backtest", "range_backtest", "live"], required=True)
    p.add_argument("--config", default="app/config/default_config.yaml")
    p.add_argument("--data", default="backtests/datasets/sample.csv", help="Entry timeframe CSV")
    p.add_argument("--htf-data", default=None, help="Higher-timeframe CSV; required for a realistic HTF-filtered backtest")
    p.add_argument("--loop", action="store_true", help="Keep paper/live engine cycling (live loops by default)")
    p.add_argument("--once", action="store_true", help="Run exactly one live/paper cycle")
    p.add_argument("--interval", type=float, default=5.0)
    p.add_argument("--backtest-profile", choices=["broker_realistic", "research_unconstrained"], default=None)
    p.add_argument("--starting-equity", type=float, default=None)
    return p


def load_frame(path: str) -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=[0]).rename(columns=lambda x: x.lower()).rename(columns={"date": "timestamp", "time": "timestamp"})
    if "timestamp" in df.columns: df = df.set_index("timestamp")
    return df.sort_index()


def main():
    args = build_parser().parse_args()
    cfg = load_settings(args.config)
    logger = setup_logging()
    if args.mode == "range_backtest":
        from app.backtest.range_backtest import run_range_backtest
        m5 = load_frame(args.data)
        range_path = args.htf_data or str(Path(args.data).with_name(Path(args.data).stem + "_H4.csv"))
        if not Path(range_path).exists():
            raise SystemExit(f"H4 data file not found: {range_path}. Supply --htf-data with real H4 data.")
        h4 = load_frame(range_path)
        r, metrics = run_range_backtest(
            m5, h4,
            starting_equity=args.starting_equity or cfg.backtest.starting_equity,
            volume=cfg.backtest.volume_min,
            point_size=cfg.point_size,
            tick_size=cfg.backtest.tick_size,
            tick_value=cfg.backtest.tick_value,
            commission_per_lot=cfg.backtest.commission_per_lot,
            slippage_points=cfg.backtest.slippage_points,
            max_sl_points=cfg.four_hour_range.max_sl_points,
            timezone=cfg.four_hour_range.timezone,
            fallback_sl_enabled=cfg.four_hour_range.fallback_sl_enabled,
            allow_multiple_per_day=cfg.four_hour_range.allow_multiple_per_day,
        )
        Path("backtests/reports").mkdir(parents=True, exist_ok=True)
        r.to_csv("backtests/reports/range4h_trades.csv", index=False)
        Path("backtests/reports/range4h_metrics.json").write_text(__import__("json").dumps(metrics, indent=2, default=str), encoding="utf-8")
        print(metrics)
        return
    if args.mode == "backtest":
        df = load_frame(args.data)
        htf_path = args.htf_data or str(Path(args.data).with_name(Path(args.data).stem + f"_{cfg.higher_timeframe}.csv"))
        if not Path(htf_path).exists():
            raise SystemExit(f"HTF data file not found: {htf_path}. Supply --htf-data with real {cfg.higher_timeframe} data.")
        htf_df = load_frame(htf_path)
        result = BacktestEngine(cfg).run(df, htf_df, starting_equity=args.starting_equity, profile=args.backtest_profile)
        Path("backtests/reports").mkdir(parents=True, exist_ok=True)
        result.to_csv("backtests/reports/trades.csv")
        result.to_json("backtests/reports/metrics.json")
        make_equity_curve(result.trades, float(result.metrics.get("starting_equity", 10_000.0)), "backtests/reports/equity.png")
        make_funnel_chart(result.metrics.get("funnel", {}), "backtests/reports/setup_funnel.png")
        event(logger, "EA", "Backtest complete", trades=result.metrics["total_trades"], net_profit=result.metrics["net_profit"])
        print(result.metrics)
        return
    if args.mode in {"paper", "live"}:
        if args.mode == "live":
            ok, errors = validate_live_config(cfg)
            if not ok:
                raise SystemExit("LIVE configuration invalid:\n" + "\n".join(errors))
            broker = MT5Broker(); broker.connect()
            if cfg.execution.require_demo_account:
                ok_demo, demo_msg = broker.validate_demo_account(cfg.execution.allowed_demo_server)
                event(logger, "EA", demo_msg)
                if not ok_demo:
                    broker.disconnect()
                    raise SystemExit("LIVE DEMO safeguard failed: " + demo_msg)
            from app.data.mt5_market_data import MT5MarketDataProvider
            provider = MT5MarketDataProvider(broker.mt5)
        else:
            broker = PaperBroker(); broker.connect()
            from app.data.market_data import MockMarketDataProvider
            frame = load_frame(args.data)
            htf_path = args.htf_data or str(Path(args.data).with_name(Path(args.data).stem + f"_{cfg.higher_timeframe}.csv"))
            if not Path(htf_path).exists():
                raise SystemExit(f"HTF data file not found: {htf_path}. Supply --htf-data for PAPER mode.")
            htf_frame = load_frame(htf_path)
            provider = MockMarketDataProvider({
                (cfg.symbol, cfg.entry_timeframe): frame,
                (cfg.symbol, cfg.higher_timeframe): htf_frame,
            })
        from app.execution.trading_engine import TradingEngine
        import time
        if args.mode == "live":
            # One engine per symbol: each symbol gets its own point size and
            # strategy state while sharing the same MT5 connection, execution
            # guard and account-level risk limits.
            engines = []
            for symbol in cfg.symbols:
                try:
                    info = broker.get_symbol_info(symbol)
                    symbol_cfg = replace(cfg, symbol=symbol, point_size=float(info.point_size))
                    engines.append(TradingEngine(symbol_cfg, provider, broker, logger))
                    event(logger, "DATA", "Symbol enabled", symbol=symbol, point_size=float(info.point_size), volume_min=float(info.volume_min), volume_step=float(info.volume_step))
                except Exception as exc:
                    if cfg.execution.skip_unavailable_symbols:
                        event(logger, "ERROR", "Skipping unavailable symbol", symbol=symbol, error=str(exc))
                        continue
                    raise
            if not engines:
                raise SystemExit("No configured FX symbol is available in MT5")
        else:
            engines = [TradingEngine(cfg, provider, broker, logger)]
        try:
            while True:
                for engine in engines:
                    engine.manage_positions()
                    engine.run_cycle()
                if args.once or (args.mode != "live" and not args.loop):
                    break
                time.sleep(max(args.interval, 0.2))
        finally:
            broker.disconnect()
        return
    broker = PaperBroker() if args.mode == "paper" else MockBroker()
    broker.connect()
    event(logger, "EA", f"Mode={args.mode.upper()}")
    if args.mode == "demo":
        print("Demo mode ready. Use app.strategy.SignalEngine with MockMarketDataProvider for deterministic simulations.")


if __name__ == "__main__":
    main()
