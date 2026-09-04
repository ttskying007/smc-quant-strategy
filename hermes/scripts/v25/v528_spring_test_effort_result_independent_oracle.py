#!/usr/bin/env python3
"""Independent raw-bar oracle for V527; does not import the generator."""
from __future__ import annotations
import csv, json
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT=Path('/root/.hermes'); KDIR=ROOT/'kline_cache'; AUD=ROOT/'smc_audit'
V527=AUD/'v527_spring_test_effort_result_seed_gate_latest.json'
OUT=AUD/f'v528_spring_test_effort_result_independent_oracle_no_write_{datetime.now():%Y%m%d_%H%M%S}'
LATEST=AUD/'v528_spring_test_effort_result_independent_oracle_latest.json'


def f(x: Any) -> float | None:
    try:
        y=float(x); return y if y>0 else None
    except (TypeError,ValueError): return None


def d(x: Any) -> str:
    x=''.join(c for c in str(x or '') if c.isdigit()); return x[:8] if len(x)>=8 else ''


def bars(symbol: str) -> list[dict[str,Any]]:
    code,ex=symbol.split('.')
    try: src=json.loads((KDIR/f'{code}_{ex}_daily_750.json').read_text())
    except Exception: return []
    out=[]
    for row in src if isinstance(src,list) else []:
        vals=[f(row.get(k)) for k in ('o','h','l','c','v')]; date=d(row.get('t') or row.get('date'))
        if date and all(v is not None for v in vals): out.append(dict(zip(('o','h','l','c','v'),vals))|{'t':date})
    return sorted(out,key=lambda x:x['t'])


def pivot_low(b: list[dict[str,Any]], i: int) -> bool:
    return i>=3 and i+3<len(b) and all(b[i]['l']<b[k]['l'] for k in range(i-3,i)) and all(b[i]['l']<=b[k]['l'] for k in range(i+1,i+4))


def raw_oracle(symbol: str) -> set[tuple[str,str,str,str,str]]:
    b=bars(symbol); pivots=[]; found=set()
    for i in range(len(b)):
        if pivot_low(b,i): pivots.append(i)
        # Pivot at i can only be used after right confirmation: i+3 < j.
        if i < 20 or not pivots:
            continue
        available=[p for p in pivots if p+3<i]
        if not available:
            continue
        p=available[-1]; low=b[p]['l']; spring=b[i]
        history=sorted(x['v'] for x in b[i-20:i])
        if len(history)!=20 or not (spring['l']<=low*.997 and spring['c']>low and spring['v']>=history[15]):
            continue
        test=None; rng=spring['h']-spring['l']
        for k in range(i+1,min(i+6,len(b))):
            x=b[k]
            if x['l']>spring['l'] and x['l']<=spring['l']+rng*.5 and x['c']>low and x['v']<spring['v']:
                test=k; break
        if test is None: continue
        sos=None
        for k in range(test+1,min(test+6,len(b))):
            if b[k]['c']>spring['h']:
                sos=k; break
        if sos is None or sos+1>=len(b): continue
        found.add((symbol,b[p]['t'],spring['t'],b[test]['t'],b[sos]['t']))
    return found


def main() -> None:
    OUT.mkdir(parents=True,exist_ok=True)
    report527=json.loads(V527.read_text())
    if not report527.get('support_gate_pass') or report527.get('outcomes_opened'):
        raise RuntimeError('V527 support/outcome contract invalid')
    rows=list(csv.DictReader(open(report527['artifacts']['seeds'],newline='')))
    expected={(r['symbol'],r['swing_date'],r['spring_date'],r['test_date'],r['sos_date']) for r in rows}
    actual=set()
    for symbol in sorted({r['symbol'] for r in rows}): actual |= raw_oracle(symbol)
    missing=sorted(expected-actual); extra=sorted(actual-expected)
    result={'version':'V528_SPRING_TEST_EFFORT_RESULT_INDEPENDENT_ORACLE_NO_WRITE','generated_at':datetime.now().isoformat(timespec='seconds'),'no_write':True,'production_write':False,'frontend_write':False,'watchlist_write':False,'outcomes_opened':False,'generator_seed_count':len(expected),'oracle_seed_count':len(actual),'missing_count':len(missing),'extra_count':len(extra),'oracle_pass':not missing and not extra,'sample_missing':missing[:10],'sample_extra':extra[:10],'decision':'V528_ORACLE_PASS__FROZEN_T1_REPLAY_ALLOWED' if not missing and not extra else 'V528_ORACLE_FAIL__CLOSE_ONTOLOGY__NO_OUTCOMES_OPENED','artifacts':{'out_dir':str(OUT),'v527':str(V527)}}
    text=json.dumps(result,ensure_ascii=False,indent=2); (OUT/'v528_report.json').write_text(text); LATEST.write_text(text); print(text)

if __name__=='__main__': main()
