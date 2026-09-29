from __future__ import annotations

import argparse
from app.config.settings import load_settings, validate_config, validate_live_config

parser = argparse.ArgumentParser()
parser.add_argument("--config", default="app/config/default_config.yaml")
parser.add_argument("--live", action="store_true", help="Also validate LIVE credentials and explicit live mode")
args = parser.parse_args()
cfg = load_settings(args.config)
ok, errors = validate_config(cfg)
if args.live:
    live_ok, live_errors = validate_live_config(cfg)
    ok = ok and live_ok
    errors.extend(live_errors)
print("VALID" if ok else "INVALID")
for err in errors: print(f"- {err}")
