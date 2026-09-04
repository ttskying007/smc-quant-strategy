#!/usr/bin/env python3
"""V65 quality metrics and hard gates."""
from __future__ import annotations
import json, statistics
from pathlib import Path
ROOT=Path('/root/.hermes')
TR=ROOT/'smc_opt_v65/v65_trades.json'
OUT=ROOT/'smc_audit/v65_quality_metrics.json'

def f(x,d=0.0):
    try:return float(x if x not in (None,'') else d)
    except:return d

def main():
    rows=json.loads(TR.read_text()) if TR.exists() else []
    wins=[r for r in rows if f(r.get('pnl_pct'))>0]
    losses=[r for r in rows if f(r.get('pnl_pct'))<=0]
    rr=[f(r.get('realized_r')) for r in rows]
    summary={
        'n':len(rows),'raw_wr':round(len(wins)/max(len(rows),1)*100,2),'qualified_wr':round(sum(1 for r in rows if r.get('qualified_win'))/max(len(rows),1)*100,2),
        'invalid_small_win_count':sum(1 for r in rows if f(r.get('pnl_pct'))>0 and not r.get('qualified_win')),
        'win_rr_below_2r':sum(1 for r in rows if f(r.get('pnl_pct'))>0 and f(r.get('realized_r'))<2),
        'small_win_below_2':sum(1 for r in rows if 0<f(r.get('pnl_pct'))<2),
        'loss_inside_1pct':sum(1 for r in rows if -1<f(r.get('pnl_pct'))<0),
        'hold_over_90':sum(1 for r in rows if int(r.get('hold_bars',0) or 0)>90),
        'avg_realized_r':round(sum(rr)/max(len(rr),1),3),'median_realized_r':round(statistics.median(rr),3) if rr else 0,
        'avg_pnl':round(sum(f(r.get('pnl_pct')) for r in rows)/max(len(rows),1),3),
        'avg_win':round(sum(f(r.get('pnl_pct')) for r in wins)/max(len(wins),1),3),
        'avg_loss':round(sum(f(r.get('pnl_pct')) for r in losses)/max(len(losses),1),3) if losses else 0,
    }
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(summary,ensure_ascii=False,indent=2))
    print(json.dumps(summary,ensure_ascii=False,indent=2))
if __name__=='__main__': main()
