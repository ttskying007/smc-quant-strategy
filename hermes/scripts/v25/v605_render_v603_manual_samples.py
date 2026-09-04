#!/usr/bin/env python3
"""Render V604 outcome-blind state-machine samples as dependency-free SVG charts."""
from __future__ import annotations

import json
from html import escape
from pathlib import Path

SAMPLES = Path('/root/.hermes/smc_audit/v604_v603_independent_semantic_audit_no_outcome_20260725_032804/v604_inspectable_chain_samples.json')
OUT = Path('/root/.hermes/smc_audit/v604_v603_independent_semantic_audit_no_outcome_20260725_032804/charts')
COLORS = {'ssl_pivot_time': '#2574a9', 'sweep_time': '#ce2b37', 'choch_time': '#7a48a8', 'ob_time': '#8b5a2b', 'fvg_time': '#e88900', 'first_touch_time': '#168f54', 'hold_time': '#0f9eaa', 'entry_time': '#111111', 'invalidated_time': '#ce2b37'}
LABELS = {'ssl_pivot_time': 'SSL', 'sweep_time': 'SWEEP', 'choch_time': 'CHOCH', 'ob_time': 'OB', 'fvg_time': 'FVG', 'first_touch_time': 'TOUCH/RECLAIM', 'hold_time': 'HOLD', 'entry_time': 'ENTRY', 'invalidated_time': 'INVALID'}
W, ROW_H, PAD = 1800, 440, 90


def render(name: str, samples: list[dict]) -> Path:
    height = ROW_H * len(samples)
    svg = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{height}" viewBox="0 0 {W} {height}">', '<rect width="100%" height="100%" fill="#fbfbfc"/>', '<style>text{font-family:Arial,sans-serif}.small{font-size:13px}.tiny{font-size:10px}</style>']
    for n, sample in enumerate(samples):
        chain, bars = sample['chain'], sample['bars']
        top, bottom = n * ROW_H + 55, (n + 1) * ROW_H - 55
        left, right = 105, W - 35
        lo = min(bar['l'] for bar in bars); hi = max(bar['h'] for bar in bars)
        if chain.get('zone_low'):
            lo = min(lo, float(chain['zone_low'])); hi = max(hi, float(chain['zone_high']))
        span = max(hi - lo, 0.01); lo -= span * .08; hi += span * .12; span = hi - lo
        sx = (right - left) / max(len(bars) - 1, 1); sy = (bottom - top) / span
        y = lambda p: bottom - (p - lo) * sy
        title = f"{chain['symbol']} | {chain['terminal_status']} | {chain.get('cancel_reason') or 'VALID'}"
        svg.append(f'<text x="{left}" y="{top-30}" class="small" font-weight="bold">{escape(title)}</text>')
        svg.append(f'<text x="{left}" y="{top-13}" class="tiny">{escape(chain["chain_key"])} | FVG [{chain.get("zone_low", "-")}, {chain.get("zone_high", "-")}]</text>')
        for g in range(5):
            p = lo + span * g / 4
            yy = y(p); svg.append(f'<line x1="{left}" y1="{yy:.1f}" x2="{right}" y2="{yy:.1f}" stroke="#e5e7eb"/><text x="8" y="{yy+4:.1f}" class="tiny">{p:.3f}</text>')
        if chain.get('zone_low'):
            zl, zh = y(float(chain['zone_low'])), y(float(chain['zone_high']))
            svg.append(f'<rect x="{left}" y="{zh:.1f}" width="{right-left}" height="{zl-zh:.1f}" fill="#f7b500" opacity=".18"/>')
        xmap = {bar['t']: left + i * sx for i, bar in enumerate(bars)}
        for i, bar in enumerate(bars):
            xx = left + i * sx; color = '#14834e' if bar['c'] >= bar['o'] else '#cf3c36'
            svg.append(f'<line x1="{xx:.1f}" y1="{y(bar["h"]):.1f}" x2="{xx:.1f}" y2="{y(bar["l"]):.1f}" stroke="{color}"/>')
            y0, y1 = y(bar['o']), y(bar['c']); svg.append(f'<rect x="{xx-sx*.32:.1f}" y="{min(y0,y1):.1f}" width="{max(sx*.64,1):.1f}" height="{max(abs(y1-y0),1):.1f}" fill="{color}"/>')
        for key, color in COLORS.items():
            t = chain.get(key, '')
            if t in xmap:
                xx = xmap[t]; svg.append(f'<circle cx="{xx:.1f}" cy="{top+5}" r="4" fill="{color}"/><text x="{xx+4:.1f}" y="{top+18}" class="tiny" fill="{color}" transform="rotate(-45 {xx+4:.1f} {top+18})">{LABELS[key]}</text>')
        for i in range(0, len(bars), max(1, len(bars)//12)):
            svg.append(f'<text x="{left+i*sx:.1f}" y="{bottom+20}" class="tiny" transform="rotate(-35 {left+i*sx:.1f} {bottom+20})">{bars[i]["t"][4:12]}</text>')
        svg.append(f'<line x1="{left}" y1="{bottom}" x2="{right}" y2="{bottom}" stroke="#555"/>')
    svg.append('</svg>')
    path = OUT / f'{name.lower()}.svg'; path.write_text('\n'.join(svg)); return path


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    data = json.loads(SAMPLES.read_text())
    print('\n'.join(str(render(name, samples)) for name, samples in data.items()))


if __name__ == '__main__':
    main()
