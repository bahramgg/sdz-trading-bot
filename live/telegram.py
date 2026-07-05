"""Telegram Level-1 alerts (master plan §4). One line, numbers only, no essays.

Format:
  [SDZ] BTCUSDT 1H DEMAND fresh s8 | prox 91250 dist 90400 | SL 90310 TP 93870 (3.1R) | DBR
"""
from __future__ import annotations

import os
from typing import Optional

from engine.lifecycle import TradePlan
from engine.zones import Zone, ZoneState


def _fmt(x: float) -> str:
    # compact price: strip trailing zeros but keep precision for FX
    s = f"{x:.5f}".rstrip("0").rstrip(".")
    return s if s else "0"


def format_zone_alert(zone: Zone, plan: TradePlan, score: int,
                      freshness_label: str = "fresh") -> str:
    sym = zone.symbol.replace("/", "")
    return (
        f"[SDZ] {sym} {zone.tf.upper()} {zone.ztype.value.upper()} "
        f"{freshness_label} s{score} | "
        f"prox {_fmt(zone.proximal)} dist {_fmt(zone.distal)} | "
        f"SL {_fmt(plan.stop)} TP {_fmt(plan.target)} ({plan.target_r:.1f}R) | "
        f"{zone.pattern.value}"
    )


def format_approach_alert(zone: Zone, distance_atr: float) -> str:
    sym = zone.symbol.replace("/", "")
    return (f"[SDZ approach] {sym} {zone.tf.upper()} {zone.ztype.value.upper()} "
            f"prox {_fmt(zone.proximal)} ~{distance_atr:.2f}ATR away | {zone.pattern.value}")


async def send(text: str, token: Optional[str] = None,
               chat_id: Optional[str] = None) -> bool:
    """Send a message via the Telegram Bot API. Returns True on success.

    Credentials come from args or TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID env.
    Import of the HTTP client is lazy so this module loads without deps.
    """
    token = token or os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = chat_id or os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return False
    import aiohttp  # lazy
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    async with aiohttp.ClientSession() as s:
        async with s.post(url, json={"chat_id": chat_id, "text": text}) as r:
            return r.status == 200
