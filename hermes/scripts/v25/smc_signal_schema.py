#!/usr/bin/env python3
"""Unified SMC signal schema helpers.

This module keeps raw trading boundaries separate from display/normalized zones.
Trading code must use raw_zone_low/raw_zone_high (or the compatibility
zone_low/zone_high populated from raw values), never display_*.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, Optional


def _f(x: Any, default: float = 0.0) -> float:
    try:
        return float(x)
    except Exception:
        return default


@dataclass
class ZoneSignal:
    symbol: str = ""
    signal_type: str = ""
    direction: str = ""
    level_type: str = ""
    structure_type: str = ""
    source_anchor_idx: Optional[int] = None
    signal_idx: Optional[int] = None
    signal_date: str = ""
    raw_zone_low: float = 0.0
    raw_zone_high: float = 0.0
    display_zone_low: Optional[float] = None
    display_zone_high: Optional[float] = None
    strength: float = 0.0
    invalidation: Optional[float] = None
    session: str = ""
    market_state: str = ""
    meta: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        # Compatibility fields for older engine functions; always raw values.
        d["type"] = self.signal_type
        d["index"] = self.signal_idx
        d["date"] = self.signal_date
        d["zone_low"] = self.raw_zone_low
        d["zone_high"] = self.raw_zone_high
        d["raw_top"] = self.raw_zone_high
        d["raw_bottom"] = self.raw_zone_low
        d["display_top"] = self.display_zone_high
        d["display_bottom"] = self.display_zone_low
        d["schema_version"] = "raw_display_split_v1"
        return d


def normalize_display_zone(raw_low: float, raw_high: float, atr: float, price: float,
                           method: str = "atr", atr_mult: float = 0.75,
                           pct: float = 0.003) -> Dict[str, float]:
    """Return a visual-only normalized zone around the raw midpoint."""
    raw_low, raw_high, atr, price = _f(raw_low), _f(raw_high), _f(atr), _f(price)
    if raw_low <= 0 or raw_high <= raw_low:
        return {"display_zone_low": raw_low, "display_zone_high": raw_high}
    height = atr * atr_mult if method == "atr" and atr > 0 else price * pct
    if height <= 0:
        height = raw_high - raw_low
    mid = (raw_low + raw_high) / 2.0
    return {"display_zone_low": mid - height / 2.0, "display_zone_high": mid + height / 2.0}


def raw_zone(z: Dict[str, Any]) -> Dict[str, float]:
    """Extract raw trading zone from any legacy/new zone dict."""
    low = _f(z.get("raw_zone_low", z.get("zone_low", z.get("gap_low", 0))))
    high = _f(z.get("raw_zone_high", z.get("zone_high", z.get("gap_high", 0))))
    return {"zone_low": low, "zone_high": high}


def attach_raw_display_fields(z: Dict[str, Any], atr: float = 0.0, price: float = 0.0) -> Dict[str, Any]:
    """Mutate/copy a legacy zone to explicit raw/display fields.

    zone_low/zone_high remain raw for backward compatibility.
    """
    out = dict(z)
    rz = raw_zone(out)
    out["raw_zone_low"] = rz["zone_low"]
    out["raw_zone_high"] = rz["zone_high"]
    out["zone_low"] = rz["zone_low"]
    out["zone_high"] = rz["zone_high"]
    out.setdefault("raw_bottom", rz["zone_low"])
    out.setdefault("raw_top", rz["zone_high"])
    if "display_zone_low" not in out or "display_zone_high" not in out:
        disp = normalize_display_zone(rz["zone_low"], rz["zone_high"], atr, price or ((rz["zone_low"] + rz["zone_high"]) / 2.0))
        out.update(disp)
    out.setdefault("display_bottom", out.get("display_zone_low"))
    out.setdefault("display_top", out.get("display_zone_high"))
    out["trade_boundary"] = "RAW_ZONE_ONLY"
    out["schema_version"] = "raw_display_split_v1"
    return out
