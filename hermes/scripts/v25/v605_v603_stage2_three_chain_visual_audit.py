#!/usr/bin/env python3
"""Render deterministic Stage-2 visual packets for three V603 lifecycle states."""
from __future__ import annotations

import csv
import gzip
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path('/root/.hermes')
RAW = ROOT / 'intraday_cache/raw_multitf_v536/source_raw/sina/m15'
AUDIT = ROOT / 'smc_audit'
INPUT = AUDIT / 'v603_ssl_choch_displacement_pristine_state_machine_latest.json'
OUT = AUDIT / 'v605_v603_stage2_visual_audit_no_write'
SAMPLES = [
    ('VALID_CHAIN', ''),
    ('CANCELLED_CHAIN', 'CANCEL_FIRST_TOUCH_FAILED_RECLAIM'),
    ('CANCELLED_CHAIN', 'CANCEL_ZONE_INVALIDATED_ON_FIRST_TOUCH'),
]
EVENTS = [
    ('ssl_pivot_time', 'SSL'), ('sweep_time', 'Sweep'), ('pre_sweep_reference_high_time', 'RefHigh'),
    ('choch_time', 'CHOCH'), ('ob_time', 'OB'), ('fvg_time', 'FVG'),
    ('first_touch_time', 'Touch'), ('reclaim_time', 'Reclaim'), ('hold_time', 'Hold'),
    ('entry_time', 'Entry'), ('invalidated_time', 'Invalid'),
]


def load_bars(symbol: str) -> list[dict]:
    path = RAW / f'{symbol.replace(".", "_")}_m15.json.gz'
    with gzip.open(path, 'rt', encoding='utf-8') as handle:
        raw = json.load(handle)
    return sorted([
        {'t': str(row['t']), 'o': float(row['o']), 'h': float(row['h']), 'l': float(row['l']), 'c': float(row['c'])}
        for row in raw if all(key in row for key in ('t', 'o', 'h', 'l', 'c'))
    ], key=lambda row: row['t'])


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    source = json.loads(INPUT.read_text())
    with Path(source['artifacts']['records']).open(encoding='utf-8', newline='') as handle:
        records = list(csv.DictReader(handle))
    selected = [next(row for row in records if row['status'] == status and row['cancel_reason'] == reason) for status, reason in SAMPLES]

    width, panel_h = 1800, 510
    image = Image.new('RGB', (width, panel_h * len(selected)), 'white')
    draw = ImageDraw.Draw(image, 'RGBA')
    font = ImageFont.load_default()
    packet = []
    for panel, row in enumerate(selected):
        y0 = panel * panel_h
        bars = load_bars(row['symbol'])
        by_time = {bar['t']: i for i, bar in enumerate(bars)}
        marked = [by_time[row[key]] for key, _ in EVENTS if row.get(key) and row[key] in by_time]
        lo, hi = max(0, min(marked) - 8), min(len(bars), max(marked) + 9)
        window = bars[lo:hi]
        zone_low, zone_high = float(row['zone_low']), float(row['zone_high'])
        p_low = min(min(bar['l'] for bar in window), zone_low)
        p_high = max(max(bar['h'] for bar in window), zone_high)
        pad = max((p_high - p_low) * 0.12, 0.01)
        p_low, p_high = p_low - pad, p_high + pad
        chart_left, chart_right = 100, width - 50
        chart_top, chart_bottom = y0 + 80, y0 + panel_h - 75
        xstep = (chart_right - chart_left) / max(len(window), 1)
        price_y = lambda price: chart_bottom - (price - p_low) / (p_high - p_low) * (chart_bottom - chart_top)
        draw.rectangle((chart_left, price_y(zone_high), chart_right, price_y(zone_low)), fill=(55, 125, 255, 46))
        for i, bar in enumerate(window):
            x = chart_left + (i + .5) * xstep
            color = (23, 132, 91, 255) if bar['c'] >= bar['o'] else (195, 75, 75, 255)
            draw.line((x, price_y(bar['h']), x, price_y(bar['l'])), fill=color, width=2)
            top, bottom = price_y(max(bar['o'], bar['c'])), price_y(min(bar['o'], bar['c']))
            draw.rectangle((x - xstep * .26, top, x + xstep * .26, max(bottom, top + 2)), fill=color)
        label_n = 0
        for key, label in EVENTS:
            timestamp = row.get(key)
            if not timestamp or timestamp not in by_time or not lo <= by_time[timestamp] < hi:
                continue
            x = chart_left + (by_time[timestamp] - lo + .5) * xstep
            draw.line((x, chart_top, x, chart_bottom), fill=(55, 55, 55, 120), width=1)
            draw.text((x + 2, chart_top + (label_n % 2) * 17), label, fill=(20, 20, 20, 255), font=font)
            label_n += 1
        title = f"{row['symbol']} | {row['status']} | {row['cancel_reason'] or 'VALID'} | FVG {zone_low:.3f}-{zone_high:.3f}"
        draw.text((20, y0 + 20), title, fill=(0, 0, 0, 255), font=font)
        draw.text((chart_left, chart_bottom + 12), '15m OHLC, deterministic first lexical packet; blue = displacement FVG zone', fill=(60, 60, 60, 255), font=font)
        packet.append({
            'symbol': row['symbol'], 'status': row['status'], 'cancel_reason': row['cancel_reason'],
            'events': {key: row[key] for key, _ in EVENTS if row.get(key)},
            'zone_low': zone_low, 'zone_high': zone_high,
        })
    png = OUT / 'v605_three_deterministic_stage2_chain_packets.png'
    image.save(png)
    report = {
        'version': 'V605_V603_STAGE2_THREE_DETERMINISTIC_CHAIN_VISUAL_AUDIT_NO_WRITE',
        'research_only': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
        'selection': 'First lexical record in V603 output for VALID_CHAIN, CANCEL_FIRST_TOUCH_FAILED_RECLAIM, and CANCEL_ZONE_INVALIDATED_ON_FIRST_TOUCH; no outcome fields used.',
        'packets': packet, 'image': str(png),
    }
    (OUT / 'v605_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
