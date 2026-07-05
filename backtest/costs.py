"""Transaction cost model (master plan §3).

Returns per-side cost in PRICE units so the simulator can (a) widen the stop by
a cost buffer (§2.6) and (b) debit realised R by the round-trip cost.
"""
from __future__ import annotations

from config import costs as _costs_cfg


def per_side_cost(market: str, symbol: str, price: float) -> float:
    """Per-side cost in price units (fees + slippage, or half-spread + slip)."""
    cfg = _costs_cfg()
    if market == "crypto":
        c = cfg["crypto"]
        fee = price * (float(c["taker_fee_pct"]) / 100.0)
        slip = price * (float(c["slippage_bps"]) / 10000.0)
        return fee + slip
    elif market == "forex":
        c = cfg["forex"]
        spread = float(c["spread"].get(symbol, 0.0))
        slip = price * (float(c["slippage_bps"]) / 10000.0)
        # spread is a round-trip cost; charge half per side
        return spread / 2.0 + slip
    raise ValueError(f"unknown market: {market}")


def round_trip_cost(market: str, symbol: str, entry: float, exit_price: float) -> float:
    return per_side_cost(market, symbol, entry) + per_side_cost(market, symbol, exit_price)
