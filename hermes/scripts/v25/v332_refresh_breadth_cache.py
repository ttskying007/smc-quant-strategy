#!/usr/bin/env python3
"""V332 refresh breadth cache from current kline cache.

Root cause found in V231/V236 current zero-supply audit: v185_market_breadth_cache
was stale, causing previous-day br_above_ma20 to remain frozen and blocking V236.
This script backs up the old cache and rebuilds breadth deterministically from
/root/.hermes/kline_cache/*_daily_750.json.

Writes only audit cache + audit report. No production/frontend/watchlist writes.
"""
from __future__ import annotations
import glob, json, shutil
from datetime import datetime
from pathlib import Path
from typing import Any
import pandas as pd
ROOT=Path('/root/.hermes'); KDIR=ROOT/'kline_cache'; AUD=ROOT/'smc_audit'; CACHE=AUD/'v185_market_breadth_cache.csv'
OUT=AUD/f"v332_breadth_cache_refresh_no_write_{datetime.now().strftime('%Y%m%d_%H%M%S')}"; LATEST=AUD/'v332_breadth_cache_refresh_latest.json'

def dn(x:Any)->str:
 s=''.join(ch for ch in str(x or '').replace('-','')[:10] if ch.isdigit()); return s[:8] if len(s)>=8 else ''
def sf(x:Any):
 try: return float(x)
 except Exception: return None

def main():
 OUT.mkdir(parents=True,exist_ok=True)
 before=pd.read_csv(CACHE) if CACHE.exists() else pd.DataFrame()
 backup=OUT/'v185_market_breadth_cache.before.csv'
 if CACHE.exists(): shutil.copy2(CACHE, backup)
 rows={}
 file_count=0
 for fp in glob.glob(str(KDIR/'*_daily_750.json')):
  file_count+=1
  try: data=json.loads(Path(fp).read_text())
  except Exception: continue
  bars=[]
  for b in data:
   d=dn(b.get('t') or b.get('date')); c=sf(b.get('c'))
   if d and c is not None and c>0: bars.append((d,c))
  bars.sort(); closes=[c for _,c in bars]
  for i,(d,c) in enumerate(bars):
   if i<19: continue
   ma=sum(closes[i-19:i+1])/20
   rows.setdefault(d,[]).append(c>ma)
 out=[]
 for d,vals in rows.items(): out.append({'breadth_date':d,'n':len(vals),'br_above_ma20':sum(vals)/len(vals)*100})
 df=pd.DataFrame(out).sort_values('breadth_date')
 df.to_csv(CACHE,index=False)
 df.to_csv(OUT/'v185_market_breadth_cache.after.csv',index=False)
 report={'version':'V332_BREADTH_CACHE_REFRESH_NO_WRITE','generated_at':datetime.now().isoformat(timespec='seconds'),'no_write':True,'production_write':False,'frontend_write':False,'watchlist_write':False,'cache_path':str(CACHE),'backup':str(backup),'file_count':file_count,'before_rows':int(len(before)),'before_last':before.tail(10).to_dict('records') if len(before) else [],'after_rows':int(len(df)),'after_first_date':str(df.breadth_date.min()) if len(df) else '', 'after_last_date':str(df.breadth_date.max()) if len(df) else '', 'after_tail':df.tail(20).to_dict('records'),'artifacts':{'out_dir':str(OUT),'latest':str(LATEST),'after_csv':str(OUT/'v185_market_breadth_cache.after.csv')}}
 (OUT/'v332_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8'); LATEST.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps(report,ensure_ascii=False,indent=2))
if __name__=='__main__': main()
