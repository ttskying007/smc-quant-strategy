#!/bin/bash
# 并行下载缺失的周线数据 (shell + curl, 20并发)
# Source: Hubble API primary, 东方财富 fallback

KLINE="/root/.hermes/kline_cache"
HUBBLE="http://43.167.234.49:3101/api/v2/cnstock/stocks"
KEY="123456"
TOTAL=0
SUCCESS_H=0
SUCCESS_EM=0
FAILED=0

# Generate task list: lines format "SYMBOL SECID"
# SECID: 0.000001 for SZ, 1.600519 for SH
TASKS=$(mktemp)
for f in "$KLINE"/*_daily_300.json; do
    name=$(basename "$f" _daily_300.json)
    code="${name%_*}"
    mkt="${name##*_}"
    sym="${code}.${mkt}"
    # Skip if weekly already exists and non-empty
    weekly_file="$KLINE/${name}_weekly_200.json"
    if [ -f "$weekly_file" ]; then
        sz=$(stat -c%s "$weekly_file" 2>/dev/null || echo 0)
        if [ "$sz" -gt 100 ]; then
            continue
        fi
    fi
    # Build secid for Eastmoney fallback: 0.xxx for SZ, 1.xxx for SH
    if [ "$mkt" = "SZ" ]; then
        secid="0.${code}"
    else
        secid="1.${code}"
    fi
    echo "$sym $secid"
    TOTAL=$((TOTAL+1))
done > "$TASKS"

echo "Missing weekly: $TOTAL stocks"
echo "Downloading with 20 parallel workers..."

download_one() {
    local sym="$1" secid="$2"
    local name="${sym//./_}"
    local out="$KLINE/${name}_weekly_200.json"
    
    # Try Hubble first
    local resp=$(curl -sS --max-time 15 \
        -H "X-API-Key: $KEY" \
        -H "Content-Type: application/json" \
        "$HUBBLE?symbol=${sym}&interval=weekly&limit=200" 2>/dev/null)
    
    if [ -n "$resp" ] && echo "$resp" | python3 -c "
import sys,json
d=json.load(sys.stdin)
bars=d.get('data',[])
if len(bars)>=10:
    o=[{'t':b['time'],'o':b['open'],'h':b['high'],'l':b['low'],'c':b['close'],'v':b.get('volume',0)} for b in bars]
    import json as j
    print(j.dumps(o))
" 2>/dev/null > "$out"; then
        local n=$(python3 -c "import json;print(len(json.load(open('$out'))))" 2>/dev/null || echo 0)
        if [ "$n" -ge 10 ]; then
            echo "OK hubble $sym ($n bars)"
            return 0
        fi
    fi
    
    # Fallback to Eastmoney
    local em_url="https://push2his.eastmoney.com/api/qt/stock/kline/get?secid=${secid}&klt=102&fqt=1&lmt=200&fields1=f1,f2&fields2=f51,f52,f53,f54,f55,f56&end=20500101"
    resp=$(curl -sS --max-time 15 "$em_url" 2>/dev/null)
    
    if [ -n "$resp" ] && echo "$resp" | python3 -c "
import sys,json
d=json.load(sys.stdin)
klines=d.get('data',{}).get('klines',[])
if len(klines)>=10:
    o=[]
    for k in klines:
        p=k.split(',')
        if len(p)>=6:
            o.append({'t':p[0].replace('-',''),'o':float(p[1]),'c':float(p[2]),'h':float(p[3]),'l':float(p[4]),'v':float(p[5])*100})
    import json as j
    print(j.dumps(o))
" 2>/dev/null > "$out"; then
        local n=$(python3 -c "import json;print(len(json.load(open('$out'))))" 2>/dev/null || echo 0)
        if [ "$n" -ge 10 ]; then
            echo "OK eastmoney $sym ($n bars)"
            return 0
        fi
    fi
    
    echo "FAIL $sym"
    return 1
}

export -f download_one
export KLINE HUBBLE KEY

# Run with xargs parallel
cat "$TASKS" | xargs -P 20 -I {} bash -c 'download_one {}' 2>&1 | while IFS= read -r line; do
    echo "$line"
done

# Count results
SUCCESS_H=$(grep -c "^OK hubble" /dev/stdin 2>/dev/null || echo 0)

rm -f "$TASKS"
