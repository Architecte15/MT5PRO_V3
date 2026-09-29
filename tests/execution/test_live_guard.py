import os
from app.config.models import AppConfig
from app.config.settings import validate_live_config


def test_live_guard_without_credentials(monkeypatch):
    for k in ("MT5_LOGIN", "MT5_PASSWORD", "MT5_SERVER"):
        monkeypatch.delenv(k, raising=False)
    cfg = AppConfig(execution_mode="live")
    ok, errors = validate_live_config(cfg)
    assert not ok
    assert errors
