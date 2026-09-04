#!/bin/bash
# 批量下载缺失股票日线 (腾讯API, 20并发)
KLINE="/root/.hermes/kline_cache"
TOTAL=0; OK=0; FAIL=0

# Generate missing code list
for code in $(seq -w 1 4000); do
    for mkt in SZ; do
        name="${code}_${mkt}"
        [ -f "$KLINE/${name}_daily_300.json" ] && continue
        # Build Tencent prefix
        [ "$mkt" = "SZ" ] && pfx="sz" || pfx="sh"
        echo "${code}.${mkt}|${pfx}${code}"
        TOTAL=$((TOTAL+1))
    done
done

for code in $(seq -w 300000 302000); do
    name="${code}_SZ"
    [ -f "$KLINE/${name}_daily_300.json" ] && continue
    echo "${code}.SZ|sz${code}"
    TOTAL=$((TOTAL+1))
done

for code in $(seq -w 600000 606000); do
    name="${code}_SH"
    [ -f "$KLINE/${name}_daily_300.json" ] && continue
    echo "${code}.SH|sh${code}"
    TOTAL=$((TOTAL+1))
done

for code in $(seq -w 688000 690000); do
    name="${code}_SH"
    [ -f "$KLINE/${name}_daily_300.json" ] && continue
    echo "${code}.SH|sh${code}"
    TOTAL=$((TOTAL+1))
done | head -5000 > /tmp/missing_stocks.txt

echo "Missing: $(wc -l < /tmp/missing_stocks.txt)"

# Download function
download_one() {
    local sym="$1" tcode="$2"
    local name="${sym//./_}"
    local out="$KLINE/${name}_daily_300.json"
    
    # Skip if already exists
    [ -f "$out" ] && { local sz=$(stat -c%s "$out" 2>/dev/null || echo 0); [ "$sz" -gt 2000 ] && return 0; }
    
    local resp=$(curl -sSL --max-time 6 \
        "http://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=${tcode},day,,,300,qfq" 2>/dev/null)
    
    [ -z "$resp" ] && return 1
    
    echo "$resp" | python3 -c "
import sys,json
d=json.load(sys.stdin)
data=d.get('data',{}).get('${tcode}',{})
bars=data.get('qfqday',data.get('day',[]))
if bars and len(bars)>=50:
    result=[]
    for b in bars:
        result.append({'t':b[0].replace('-',''),'o':float(b[1]),'c':float(b[2]),
                       'h':float(b[3]),'l':float(b[4]),'v':float(b[5])*100 if len(b)>5 else 0})
    open('${out}','w').write(json.dumps(result))
    print('OK')
" 2>/dev/null
}

export -f download_one
export KLINE

echo "Downloading with 20 workers..."
cat /tmp/missing_stocks.txt | head -3000 | \
    while IFS='|' read sym tcode; do
        echo "$sym $tcode"
    done | xargs -P20 -n2 bash -c 'download_one "$1" "$2"' _ 2>&1 | grep -c "OK"
