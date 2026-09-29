from __future__ import annotations

import argparse
from pathlib import Path
import pandas as pd

from app.config.settings import load_settings
from app.strategy.liquidity_flow.dataset import build_observation_dataset, save_dataset
from app.strategy.liquidity_flow.experiments import run_experiments, walk_forward


def load_frame(path: str) -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=[0]).rename(columns=lambda x: x.lower())
    df = df.rename(columns={"date": "timestamp", "time": "timestamp"})
    return df.set_index("timestamp").sort_index()


def main() -> None:
    p = argparse.ArgumentParser(description="Liquidity Flow research pipeline; never enables live trading")
    p.add_argument("--data", required=True)
    p.add_argument("--config", default="app/config/default_config.yaml")
    p.add_argument("--horizon", type=int, default=None)
    p.add_argument("--output", default="backtests/research/liquidity_flow_dataset.csv")
    args = p.parse_args()
    cfg = load_settings(args.config)
    df = load_frame(args.data)
    horizon = args.horizon or cfg.liquidity_flow.outcome_horizon_bars
    dataset = build_observation_dataset(df, cfg, horizon)
    save_dataset(dataset, args.output)
    exp = run_experiments(dataset)
    wf, status = walk_forward(dataset, cfg.liquidity_flow.min_samples)
    out = Path(args.output).parent
    out.mkdir(parents=True, exist_ok=True)
    exp.to_csv(out / "liquidity_flow_experiments.csv", index=False)
    wf.to_csv(out / "liquidity_flow_walk_forward.csv", index=False)
    (out / "liquidity_flow_validation.json").write_text(__import__("json").dumps(status, indent=2, default=str), encoding="utf-8")
    print(exp.to_string(index=False))
    print("\nWALK-FORWARD")
    print(wf.to_string(index=False))
    print(f"\nEDGE STATUS: {status["status"]}")
    print(f"Dataset: {args.output}")


if __name__ == "__main__":
    main()
