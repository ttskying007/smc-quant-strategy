#!/usr/bin/env python3
"""Render outcome-blind V603/V604 chain windows as dependency-free SVG charts."""
from __future__ import annotations

import html
import json
from datetime import datetime
from pathlib import Path

ROOT = Path('/root/.hermes')
AUDIT = ROOT / 'smc_audit'
V604 = AUDIT / 'v604_v603_independent_semantic_audit_latest.json'
OUT = AUDIT / f'v607_v603_manual_chain_chart_export_no_outcome_{datetime.now():%Y%m%d_%H%M%S}'
LATEST = AUDIT / 'v607_v603_manual_chain_chart_export_latest.json'
MARKERS = {
    'ssl_pivot_time': ('SSL', '#6c757d'), 'sweep_time': ('SWEEP', '#d62728'),
    'choch_time': ('CHOCH', '#2ca02c'), 'ob_time': ('OB', '#9467bd'),
    'fvg_time': ('FVG', '#17becf'), 'first_touch_time': ('TOUCH', '#ff7f0e'),
    'hold_time': ('HOLD', '#1f77b4'), 'entry_time': ('ENTRY', '#111111'),
    'invalidated_time': ('CANCEL', '#d62728'),
}


def esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def render(group: str, samples: list[dict]) -> Path:
    width, panel_height, pad = 1800, 390, 60
    height = 80 + len(samples) * panel_height
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
             '<rect width="100%" height="100%" fill="white"/>',
             f'<text x="30" y="38" font-family="sans-serif" font-size="24" font-weight="bold">V603 outcome-blind semantic windows — {esc(group)}</text>']
    for serial, sample in enumerate(samples):
        chain, bars = sample['chain'], sample['bars']
        top, left, right, bottom = 65 + serial * panel_height, 85, 30, 80
        chart_h, chart_w = panel_height - bottom - 24, width - left - right
        low = min(bar['l'] for bar in bars); high = max(bar['h'] for bar in bars)
        spread = max(high - low, max(high * 0.005, 0.01)); low -= spread * 0.08; high += spread * 0.12
        y = lambda value: top + (high - value) / (high - low) * chart_h
        x = lambda index: left + (index + 0.5) * chart_w / len(bars)
        candle_width = max(2, chart_w / len(bars) * 0.60)
        title = f"{chain['symbol']} — {chain['terminal_status']} {chain.get('cancel_reason', '')}"
        parts.append(f'<text x="{left}" y="{top - 8}" font-family="sans-serif" font-size="17" font-weight="bold">{esc(title)}</text>')
        if chain.get('zone_low'):
            zlow, zhigh = float(chain['zone_low']), float(chain['zone_high'])
            parts.append(f'<rect x="{left}" y="{y(zhigh):.2f}" width="{chart_w}" height="{y(zlow)-y(zhigh):.2f}" fill="#17becf" fill-opacity="0.18"/>')
        for p in range(5):
            price = low + (high - low) * p / 4
            parts.append(f'<line x1="{left}" y1="{y(price):.2f}" x2="{left + chart_w}" y2="{y(price):.2f}" stroke="#d0d0d0" stroke-width="1"/>')
            parts.append(f'<text x="5" y="{y(price)+4:.2f}" font-family="sans-serif" font-size="12">{price:.3f}</text>')
        times = [bar['t'] for bar in bars]
        for index, bar in enumerate(bars):
            color = '#d62728' if bar['c'] < bar['o'] else '#2ca02c'
            center = x(index); yopen, yclose = y(bar['o']), y(bar['c'])
            parts.append(f'<line x1="{center:.2f}" y1="{y(bar["h"]):.2f}" x2="{center:.2f}" y2="{y(bar["l"]):.2f}" stroke="{color}" stroke-width="1.2"/>')
            parts.append(f'<rect x="{center-candle_width/2:.2f}" y="{min(yopen,yclose):.2f}" width="{candle_width:.2f}" height="{max(abs(yclose-yopen),1):.2f}" fill="{color}"/>')
        for field, (label, color) in MARKERS.items():
            at = chain.get(field, '')
            if at in times:
                center = x(times.index(at))
                parts.append(f'<line x1="{center:.2f}" y1="{top}" x2="{center:.2f}" y2="{top+chart_h}" stroke="{color}" stroke-width="1.4"/>')
                parts.append(f'<text x="{center+3:.2f}" y="{top+14}" font-family="sans-serif" font-size="12" fill="{color}" transform="rotate(90 {center+3:.2f},{top+14})">{label}</text>')
        for index in range(0, len(times), max(1, len(times) // 10)):
            parts.append(f'<text x="{x(index)-20:.2f}" y="{top+chart_h+20}" font-family="sans-serif" font-size="11">{times[index][4:12]}</text>')
        parts.append(f'<text x="{left}" y="{top+chart_h+44}" font-family="sans-serif" font-size="12" fill="#444">zone={esc(chain.get("zone_low", ""))}–{esc(chain.get("zone_high", ""))}; window={esc(sample["window_start"])}–{esc(sample["window_end"])}</text>')
    parts.append('</svg>')
    path = OUT / f'{group.lower()}_manual_windows.svg'
    path.write_text('\n'.join(parts), encoding='utf-8')
    return path


def main() -> None:
    report = json.loads(V604.read_text())
    source = Path(report['artifacts']['samples'])
    payload = json.loads(source.read_text())
    OUT.mkdir(parents=True, exist_ok=False)
    charts = {group: str(render(group, rows)) for group, rows in payload.items()}
    report = {
        'version': 'V607_V603_MANUAL_CHAIN_CHART_EXPORT_NO_OUTCOME',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'research_only': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
        'input_contract': 'V604 inspectable source-isolated m15 chain windows only; no outcome/trade/PnL/stop/target/exit inputs.',
        'groups': {group: len(rows) for group, rows in payload.items()}, 'charts': charts, 'source': str(source),
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    (OUT / 'v607_report.json').write_text(text)
    LATEST.write_text(text)
    print(text)


if __name__ == '__main__':
    main()
