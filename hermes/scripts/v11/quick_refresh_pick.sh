#!/bin/bash
# 快速: xargs -P20 刷新日线 + 扫描选股
# 2026-05-14

KLINE="/root/.hermes/kline_cache"
OUT="/root/.hermes/smc_opt_v21"
TODAY="20260514"

echo "=== Phase 1: 刷新日线 (xargs -P20) ==="

# Generate refresh commands
TASKS=$(mktemp)
for f in "$KLINE"/*_daily_300.json; do
    name=$(basename "$f" _daily_300.json)
    code="${name%_*}"
    mkt="${name##*_}"
    pfx="sz"
    [ "$mkt" = "SH" ] && pfx="sh"
    sym="${code}.${mkt}"
    out="$KLINE/${name}_daily_300.json"
    
    # Check if already fresh (today's data)
    last_date=$(python3 -c "
import json
try:
    d=json.load(open('$out'))
    t=str(d[-1].get('t',d[-1].get('date','')))[:8]
    print(t)
except: print('00000000')
" 2>/dev/null)
    
    if [ "$last_date" -ge "$TODAY" ]; then
        echo "$sym FRESH"
        continue
    fi
    
    # Build curl command
    echo "$sym|curl -sSL --max-time 8 'http://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=${pfx}${code},day,,,300,qfq' | python3 -c \"
import sys,json
d=json.load(sys.stdin)
data=d.get('data',{}).get('${pfx}${code}',{})
bars=data.get('qfqday',data.get('day',[]))
if bars and len(bars)>=50:
    result=[]
    for b in bars:
        result.append({'t':b[0].replace('-',''),'o':float(b[1]),'c':float(b[2]),'h':float(b[3]),'l':float(b[4]),'v':float(b[5])*100 if len(b)>5 else 0})
    import json as j
    open('$out','w').write(j.dumps(result))
    print('OK')
else:
    print('FAIL')
\""
done > "$TASKS"

total=$(wc -l < "$TASKS")
echo "  Tasks: $total"
cat "$TASKS" | head -200 | grep -v FRESH | cut -d'|' -f2- | xargs -P20 -I {} bash -c '{}' 2>&1 | grep -c "OK" &

# Wait a bit then run scanner
sleep 60

echo ""
echo "=== Phase 2: 扫描选股 ==="
cd /root/.hermes/scripts/v11 && python3 quick_pick.py 2>&1

rm -f "$TASKS"
