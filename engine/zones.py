"""Zone data model and lifecycle state (master plan §2.3, §2.4)."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


class ZoneType(Enum):
    DEMAND = "demand"
    SUPPLY = "supply"


class Pattern(Enum):
    DBR = "DBR"   # drop-base-rally  (demand, reversal)
    RBR = "RBR"   # rally-base-rally (demand, continuation)
    RBD = "RBD"   # rally-base-drop  (supply, reversal)
    DBD = "DBD"   # drop-base-drop   (supply, continuation)


class ZoneState(Enum):
    FRESH = "fresh"
    TESTED = "tested"
    BROKEN = "broken"
    CONSUMED = "consumed"
    EXPIRED = "expired"


@dataclass
class Zone:
    symbol: str
    tf: str
    ztype: ZoneType
    pattern: Pattern

    # boundaries (§2.3)
    proximal: float          # price nearest to approach (entry line)
    distal: float            # far edge (stop side)

    # provenance indices into the classified candle list
    leg_in_index: int
    base_start: int
    base_end: int
    leg_out_index: int       # == confirm_index; zone is born at this candle's close
    confirm_ts: int
    atr_at_confirm: float

    # lifecycle (§2.4)
    state: ZoneState = ZoneState.FRESH
    test_count: int = 0
    broken_index: Optional[int] = None
    expired_index: Optional[int] = None

    # scoring (§2.5) — filled by score.py at decision time
    score: Optional[int] = None
    score_breakdown: dict = field(default_factory=dict)

    @property
    def confirm_index(self) -> int:
        return self.leg_out_index

    @property
    def base_len(self) -> int:
        return self.base_end - self.base_start + 1

    @property
    def height(self) -> float:
        return abs(self.proximal - self.distal)

    def contains(self, price: float) -> bool:
        """True if price is within the [proximal, distal] band (inclusive)."""
        lo, hi = sorted((self.proximal, self.distal))
        return lo <= price <= hi
