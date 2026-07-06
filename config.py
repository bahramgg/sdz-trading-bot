"""Central config loader. Reads config/*.yaml once and exposes typed accessors.

Every named constant in the master plan lives in config/params.yaml; nothing
in the engine hardcodes a magic number that belongs there.
"""
from __future__ import annotations

import copy
import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import yaml

_ROOT = os.path.dirname(os.path.abspath(__file__))
_CONFIG_DIR = os.path.join(_ROOT, "config")


def _load_yaml(name: str) -> dict:
    path = os.path.join(_CONFIG_DIR, name)
    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


@lru_cache(maxsize=None)
def _params_raw() -> dict:
    return _load_yaml("params.yaml")


@lru_cache(maxsize=None)
def watchlist() -> dict:
    return _load_yaml("watchlist.yaml")


@lru_cache(maxsize=None)
def costs() -> dict:
    return _load_yaml("costs.yaml")


@dataclass(frozen=True)
class Params:
    """Immutable snapshot of the mechanical rule parameters (master plan §2).

    Construct the default set with ``Params.load()``. Calibration (P3) produces
    variants with ``.override(...)`` — the engine reads only from an instance,
    never from globals, so a sweep is just many instances.
    """

    atr_period: int
    erc_atr_mult: float
    erc_body_min: float
    base_body_max: float
    base_atr_max: float
    max_base_candles: int
    zone_max_atr: float
    proximal_mode: str
    zone_max_age_bars_default: int
    min_score: int
    ema_period: int
    stop_buffer_atr: float
    tp_mode: str
    tp_hybrid_floor_r: float
    exit_mode: str
    scale_tp1_r: float
    scale_fraction: float
    scale_move_be: bool
    alert_min_score: int
    approach_atr: float

    @staticmethod
    def load() -> "Params":
        p = _params_raw()
        return Params(
            atr_period=int(p["atr_period"]),
            erc_atr_mult=float(p["erc_atr_mult"]),
            erc_body_min=float(p["erc_body_min"]),
            base_body_max=float(p["base_body_max"]),
            base_atr_max=float(p["base_atr_max"]),
            max_base_candles=int(p["max_base_candles"]),
            zone_max_atr=float(p["zone_max_atr"]),
            proximal_mode=str(p["proximal_mode"]),
            zone_max_age_bars_default=int(p["zone_max_age_bars"]["default"]),
            min_score=int(p["min_score"]),
            ema_period=int(p["ema_period"]),
            stop_buffer_atr=float(p["stop_buffer_atr"]),
            tp_mode=str(p["tp_mode"]),
            tp_hybrid_floor_r=float(p["tp_hybrid_floor_r"]),
            exit_mode=str(p.get("exit_mode", "setforget")),
            scale_tp1_r=float(p.get("scale_tp1_r", 1.0)),
            scale_fraction=float(p.get("scale_fraction", 0.5)),
            scale_move_be=bool(p.get("scale_move_be", True)),
            alert_min_score=int(p["alert_min_score"]),
            approach_atr=float(p["approach_atr"]),
        )

    def override(self, **kwargs: Any) -> "Params":
        """Return a new Params with the given fields replaced (for P3 sweeps)."""
        data = copy.copy(self.__dict__)
        for k, v in kwargs.items():
            if k not in data:
                raise KeyError(f"unknown param: {k}")
            data[k] = v
        return Params(**data)


def validation_window() -> dict:
    return _params_raw()["validation"]
