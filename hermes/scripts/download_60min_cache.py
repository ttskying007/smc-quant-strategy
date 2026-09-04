#!/usr/bin/env python3
"""
Download 60min K-line for test stocks using akshare
Batch cache for V17 multi-TF testing
"""
import sys, json, time
from pathlib import Path

sys.path.insert(0, '/root/.hermes/scripts')
import akshare as ak

CACHE_DIR = Path('/root/.hermes/kline_cache')
# 200 test stocks (same as backtesting)
TEST_STOCKS = [
    "000001","000002","000004","000006","000007","000008","000009","000010",
    "000011","000012","000014","000016","000017","000019","000020","000021",
    "000025","000026","000027","000029","000030","000031","000032","000034",
    "000035","000036","000037","000039","000042","000045","000048","000049",
    "000050","000055","000056","000059","000061","000062","000063","000065",
    "000066","000068","000069","000070","000078","000088","000089","000090",
    "000096","000099","000100","000151","000153","000155","000156","000157",
    "000158","000159","000166","000301","000333","000338","000400","000401",
    "000403","000404","000407","000408","000409","000410","000411","000415",
    "000419","000420","000421","000422","000423","000425","000426","000428",
    "000429","000430","000488","000498","000501","000503","000504","000505",
    "000506","000507","000510","000513","000514","000516","000517","000518",
    "000519","000520","000521","000524","000525","000526","000528","000529",
    "000530","000531","000533","000534","000536","000537","000538","000541",
    "000543","000544","000545","000546","000547","000550","000551","000553",
    "000555","000557","000558","000559","000560","000564","000565","000566",
    "000567","000568","000570","000571","000572","000573","000576","000581",
    "000582","000586","000589","000590","000591","000592","000595","000596",
    "000597","000598","000599","000600","000603","000605","000607","000608",
    "000609","000610","000612","000617","000619","000620","000625","000626",
    "000628","000629","000630","000631","000632","000633","000635","000636",
    "000637","000638","000639","000650","000651","000652","000656","000659",
    "000661","000663","000665","000668","000669","000670","000672","000676",
    "000677","000678","000679","000680","000681","000682","000683","000685",
    "000686","000692","000695","000697","000698","000700","000701","000702",
]

def download_60min(symbol):
    """Download and cache 60min data for a symbol"""
    fname = f"{symbol}_SZ_60min_500.json"
    fpath = CACHE_DIR / fname
    if fpath.exists():
        return True  # Already cached
    
    try:
        df = ak.stock_zh_a_hist_min_em(symbol=symbol, period="60",
                                        start_date="20260101", end_date="20260508", adjust="")
        if df is None or len(df) < 50:
            return False
        
        records = []
        for _, row in df.iterrows():
            records.append({
                't': row['时间'],
                'o': float(row['开盘']),
                'h': float(row['最高']),
                'l': float(row['最低']),
                'c': float(row['收盘']),
                'v': float(row['成交量']),
            })
        
        json.dump(records[-500:], open(fpath, 'w'))
        return True
    except Exception as e:
        print(f"  FAIL {symbol}: {str(e)[:50]}")
        return False


def main():
    # First download for existing cache stocks (SZ)
    print(f"Downloading 60min data for {len(TEST_STOCKS)} test stocks...")
    print("(Note: only SZ stocks, SH stocks use A.B. suffix)")
    
    success = 0
    for i, sym in enumerate(TEST_STOCKS):
        # Try SZ first
        fname = f"{sym}_SZ_60min_500.json"
        fpath = CACHE_DIR / fname
        
        if fpath.exists():
            success += 1
            continue
        
        ok = download_60min(sym)
        if ok:
            success += 1
        else:
            # Try SH
            fname2 = f"{sym}_SH_60min_500.json"
            fpath2 = CACHE_DIR / fname2
            if not fpath2.exists():
                try:
                    df2 = ak.stock_zh_a_hist_min_em(symbol=sym, period="60",
                                                     start_date="20260101", end_date="20260508", adjust="")
                    if df2 is not None and len(df2) >= 50:
                        records = [{'t':r['时间'],'o':float(r['开盘']),'h':float(r['最高']),
                                    'l':float(r['最低']),'c':float(r['收盘']),'v':float(r['成交量'])}
                                   for _,r in df2.iterrows()]
                        json.dump(records[-500:], open(fpath2, 'w'))
                        success += 1
                except: pass
        
        if (i+1) % 10 == 0:
            print(f"  [{i+1}/{len(TEST_STOCKS)}] {success} cached so far...")
            time.sleep(1)  # rate limit
    
    print(f"\nDone: {success}/{len(TEST_STOCKS)} stocks cached")

if __name__ == '__main__':
    main()
