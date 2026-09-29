from __future__ import annotations

from app.execution.mock_broker import MockBroker


class PaperBroker(MockBroker):
    """Simulated broker. It never calls an external trading API."""
    pass
