from __future__ import annotations

import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


def setup_logging(level: str = "INFO", log_dir: str | Path = "logs", json_mode: bool = False) -> logging.Logger:
    Path(log_dir).mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("python_trading_engine")
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    if logger.handlers:
        return logger
    console = logging.StreamHandler()
    file_handler = RotatingFileHandler(Path(log_dir) / "trading.log", maxBytes=5_000_000, backupCount=5, encoding="utf-8")
    fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
    console.setFormatter(fmt); file_handler.setFormatter(fmt)
    logger.addHandler(console); logger.addHandler(file_handler)
    return logger


def event(logger: logging.Logger, category: str, message: str, **fields) -> None:
    suffix = "" if not fields else " | " + " | ".join(f"{k}={v}" for k, v in fields.items())
    logger.info(f"[{category}] {message}{suffix}")
