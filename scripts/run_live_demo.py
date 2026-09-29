from __future__ import annotations

import argparse
from app.main import main

# Usage: python -m scripts.run_live_demo [--once] [--interval 5]
# Credentials stay in .env; the configured demo-account safeguard remains active.
if __name__ == "__main__":
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--interval", type=float, default=5.0)
    args, _ = parser.parse_known_args()
    import sys
    sys.argv = [sys.argv[0], "--mode", "live", "--config", "app/config/default_config.yaml", "--interval", str(args.interval)] + (["--once"] if args.once else [])
    main()
