"""Liquidity Flow research package.

STRICTLY PARALLEL TO THE LIVE ENGINE: nothing in this package is imported by
app.main, TradingEngine or SignalEngine. Every hypothesis here must survive
train/validation/OOS/holdout and beat random controls before any deployment
discussion (see research/README.md).
"""
