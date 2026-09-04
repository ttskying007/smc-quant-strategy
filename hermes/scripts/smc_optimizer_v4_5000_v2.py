#!/usr/bin/env python3
"""
SMC V4 — 5000只全覆盖优化器 v2 (高速版)
==========================================
核心加速:
  1. 多线程并发下载 (16线程)
  2. K线缓存本地 (避免重复下载)
  3. 只做strict快速检测 (跳过无关信号)
  4. 自适应参数调优 (每只股票独立调优)
  5. 渐进式淘汰 (前期快速过滤)

速度目标: 5000只 < 60分钟

用法:
  python3 smc_optimizer_v4_5000_v2.py            # 完整5000只
  python3 smc_optimizer_v4_5000_v2.py --quick    # 快速500只
"""

import sys, os, json, random, math, time, copy, threading, concurrent.futures
from pathlib import Path
from datetime import datetime

SCRIPT_DIR = os.path.expanduser('~/.hermes/scripts')
sys.path.insert(0, SCRIPT_DIR)

for k in ['http_proxy','https_proxy','HTTP_PROXY','HTTPS_PROXY']:
    os.environ.pop(k, None)

# 直接从smc_engine_v4导入核心函数
from smc_engine_v4 import (
    get_klines, get_stock_list,
    get_volatility_profile, get_adaptive_params,
    detect_entries_v4, backtest_v4, evaluate, compute_v4_score,
    detect_fvg_standard, detect_sweep_precise, detect_ob_v4,
    detect_choch_v4, calc_bpr_v4, calc_atr
)

OPT_DIR = Path.home() / '.hermes' / 'smc_opt_v4'
OPT_DIR.mkdir(parents=True, exist_ok=True)

# 本地K线缓存
KLINE_CACHE = Path.home() / '.hermes' / 'kline_cache'
KLINE_CACHE.mkdir(parents=True, exist_ok=True)

# 多线程控制
MAX_WORKERS = 16
CACHE_LOCK = threading.Lock()


def get_klines_cached(symbol, interval='daily', limit=300):
    """带缓存的K线获取"""
    cache_key = f"{symbol}_{interval}_{limit}"
    cache_path = KLINE_CACHE / f"{cache_key.replace('.','_').replace('-','_')}.json"
    
    with CACHE_LOCK:
        if cache_path.exists() and os.path.getsize(cache_path) > 100:
            try:
                with open(cache_path) as f:
                    bars = json.load(f)
                    if len(bars) >= 100:
                        return bars
            except:
                pass
    
    try:
        bars = get_klines(symbol, interval, limit)
        if bars and len(bars) >= 100:
            with CACHE_LOCK:
                with open(cache_path, 'w') as f:
                    # save only essential fields
                    simple = [{'o':b['o'],'h':b['h'],'l':b['l'],'c':b['c'],'v':b['v'],'t':b['t']} for b in bars]
                    json.dump(simple, f, ensure_ascii=False)
        return bars
    except:
        return []


def quick_detect(bars):
    """
    快速检测: 只用strict模式, 返回是否有信号+WR
    不做完整回测, 只做一次pass
    """
    if len(bars) < 120:
        return None
    
    vol = get_volatility_profile(bars)
    ap = get_adaptive_params(vol)
    
    # 用自适应参数, threshold从3.7改为动态
    v4_params = {
        'fvg_threshold': ap.get('fvg_threshold', 0.26),
        'score_threshold': ap.get('score_threshold', 3.0),
        'sl_mult': ap.get('sl_mult', 2.5),
        'tp_mult': ap.get('tp_mult', 2.1),
    }
    
    strict_trades = backtest_v4(bars, 'strict', v4_params)
    
    if not strict_trades or len(strict_trades) < 1:
        return None
    
    wins = sum(1 for t in strict_trades if t['pnl'] > 0)
    n = len(strict_trades)
    wr = wins/n*100
    
    losses = [t for t in strict_trades if t['pnl'] <= 0]
    pf = abs(sum(t['pnl'] for t in strict_trades if t['pnl']>0) / 
             sum(t['pnl'] for t in losses)) if losses and sum(t['pnl'] for t in losses)!=0 else 999
    
    avg = sum(t['pnl'] for t in strict_trades)/n
    std = math.sqrt(sum((t['pnl']-avg)**2 for t in strict_trades)/n) if n>1 else 0.001
    sr = (avg/std)*math.sqrt(252) if std>0 else 0
    
    return {
        'code': code_global if 'code_global' in dir() else symbol,
        'n_s': n, 'wr_s': round(wr,1), 'pf_s': round(pf,2), 'sr_s': round(sr,2),
        'vol_level': vol['vol_level'], 'atr_pct': vol['atr_pct'],
        'trend': vol['trend_strength'],
    }


def process_single_stock(code_name):
    """处理单只股票"""
    code, name = code_name
    try:
        bars = get_klines_cached(code, 'daily', 300)
        if not bars or len(bars) < 120:
            return {'code': code, 'name': name, 'error': 'data'}
        
        vol = get_volatility_profile(bars)
        ap = get_adaptive_params(vol)
        
        v4_params = {
            'fvg_threshold': ap.get('fvg_threshold', 0.26),
            'score_threshold': max(2.5, ap.get('score_threshold', 3.0)),
            'sl_mult': 2.5,
            'tp_mult': 2.1,
        }
        
        strict_trades = backtest_v4(bars, 'strict', v4_params)
        
        result = {
            'code': code, 'name': name,
            'vol_level': vol['vol_level'], 'atr_pct': vol['atr_pct'],
            'trend': vol['trend_strength'],
            'n_s': 0, 'wr_s': 0, 'pf_s': 0, 'sr_s': 0,
            'n_t': 0, 'wr_t': 0,
        }
        
        if strict_trades and len(strict_trades) >= 1:
            result['n_s'] = len(strict_trades)
            wins = [t for t in strict_trades if t['pnl']>0]
            result['wr_s'] = round(len(wins)/len(strict_trades)*100, 1)
            losses = [t for t in strict_trades if t['pnl']<=0]
            result['pf_s'] = round(abs(sum(t['pnl'] for t in strict_trades if t['pnl']>0)/sum(t['pnl'] for t in losses)) if losses and sum(t['pnl'] for t in losses)!=0 else 999, 2)
            avg = sum(t['pnl'] for t in strict_trades)/len(strict_trades)
            std = math.sqrt(sum((t['pnl']-avg)**2 for t in strict_trades)/len(strict_trades)) if len(strict_trades)>1 else 0.001
            result['sr_s'] = round((avg/std)*math.sqrt(252) if std>0 else 0, 3)
        
        # total mode
        total_trades = backtest_v4(bars, 'total', v4_params)
        if total_trades:
            result['n_t'] = len(total_trades)
            wins_t = [t for t in total_trades if t['pnl']>0]
            result['wr_t'] = round(len(wins_t)/len(total_trades)*100, 1)
        
        return result
    
    except Exception as e:
        return {'code': code, 'name': name, 'error': str(e)[:30]}


class V4MassScanner:
    """5000只大规模扫描器"""
    
    def __init__(self, quick=False):
        self.quick = quick
        self.all_stocks = []
        self.results = []
        self.signal_count = 0
        self.no_signal_count = 0
        self.error_count = 0
        self.start_time = time.time()
        self.lock = threading.Lock()
        self.processed = 0
        self.total = 0
    
    def load(self):
        stocks = get_stock_list()
        self.all_stocks = [(s['symbol'], s.get('name','')) for s in stocks 
                          if not s.get('symbol','').startswith('*ST')]
        random.shuffle(self.all_stocks)
        
        if self.quick:
            self.all_stocks = self.all_stocks[:500]
        
        self.total = len(self.all_stocks)
        print(f"  Total stocks: {self.total}")
    
    def on_complete(self, future):
        """回调: 处理完成"""
        with self.lock:
            self.processed += 1
            try:
                r = future.result()
                if r and r.get('error'):
                    self.error_count += 1
                elif r and r['n_s'] > 0:
                    self.results.append(r)
                    self.signal_count += 1
                else:
                    self.no_signal_count += 1
            except:
                self.error_count += 1
    
    def run(self):
        self.load()
        
        print(f"\n{'='*70}")
        print(f"  SMC V4 — 5000只全覆盖扫描 v2")
        print(f"  Workers: {MAX_WORKERS} | K线: 300日 | Cache: {KLINE_CACHE}")
        print(f"{'='*70}")
        
        start = time.time()
        last_report = 0
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = [executor.submit(process_single_stock, s) for s in self.all_stocks]
            
            for f in concurrent.futures.as_completed(futures):
                self.on_complete(f)
                
                # 每20只或5%报告
                elapsed = time.time() - start
                if self.processed - last_report >= 20:
                    last_report = self.processed
                    pct = self.processed/self.total*100
                    rate = self.processed/elapsed if elapsed > 0 else 0
                    eta = (self.total - self.processed)/rate if rate > 0 else 0
                    
                    has_sig = len(self.results)
                    sig_pct = has_sig/max(1, self.processed - self.error_count)*100 if self.processed > self.error_count else 0
                    
                    # avg WR of current results
                    if self.results:
                        avg_wr = sum(r['wr_s'] for r in self.results)/len(self.results)
                        wr80 = sum(1 for r in self.results if r['wr_s']>=80)/len(self.results)*100
                        wr100 = sum(1 for r in self.results if r['wr_s']==100)/len(self.results)*100
                        total_sig = sum(r['n_s'] for r in self.results)
                    else:
                        avg_wr = wr80 = wr100 = total_sig = 0
                    
                    bar_len = 30
                    filled = int(bar_len * self.processed / self.total)
                    bar = '█' * filled + '░' * (bar_len - filled)
                    
                    print(f"  [{self.processed:>4d}/{self.total}] {pct:>5.1f}% {bar} "
                          f"sig={has_sig}({sig_pct:.0f}%) err={self.error_count} "
                          f"WR={avg_wr:.1f}% WR80={wr80:.0f}% WR100={wr100:.0f}% "
                          f"nSig={total_sig} {rate:.1f}stk/s ETA={eta:.0f}s")
                
                if self.processed >= self.total:
                    break
        
        total_time = time.time() - start
        self.final_report(total_time)
    
    def final_report(self, total_time):
        print(f"\n{'='*70}")
        print(f"  🏁 SMC V4 — 5000只全覆盖完成!")
        print(f"  耗时: {total_time/60:.1f}分钟")
        print(f"{'='*70}")
        
        print(f"\n📊 覆盖统计:")
        print(f"  总股票:     {self.total}")
        print(f"  已完成:     {self.processed}")
        print(f"  有信号:     {self.signal_count} ({self.signal_count/max(1,self.processed-self.error_count)*100:.1f}%)")
        print(f"  无信号:     {self.no_signal_count}")
        print(f"  错误:       {self.error_count}")
        
        if self.results:
            wr_s_list = [r['wr_s'] for r in self.results]
            n_s_list = [r['n_s'] for r in self.results]
            
            avg_wr = sum(wr_s_list)/len(wr_s_list)
            med_wr = sorted(wr_s_list)[len(wr_s_list)//2]
            wr80 = sum(1 for r in self.results if r['wr_s']>=80)/len(self.results)*100
            wr100 = sum(1 for r in self.results if r['wr_s']==100)/len(self.results)*100
            total_sig = sum(n_s_list)
            
            print(f"\n📊 V4信号质量 (strict):")
            print(f"  中位数WR:   {med_wr:.1f}%")
            print(f"  平均WR:     {avg_wr:.1f}%")
            print(f"  WR>=80%:    {wr80:.1f}% 的股票")
            print(f"  WR=100%:    {wr100:.1f}% 的股票")
            print(f"  总信号数:   {total_sig}")
            print(f"  平均N:      {sum(n_s_list)/len(n_s_list):.1f} 笔/股")
            print(f"  总盈利:     ...")
            
            # WR分布
            print(f"\n📊 WR分布:")
            wr_s_sorted = sorted(wr_s_list)
            percentiles = [1, 5, 10, 25, 50, 75, 90, 95, 99]
            for p in percentiles:
                idx = int(len(wr_s_sorted) * p / 100)
                print(f"    {p:>2d}th percentile: {wr_s_sorted[min(idx, len(wr_s_sorted)-1)]:>5.1f}%")
            
            # 按波动率
            print(f"\n📊 按波动率:")
            for vl in ['low', 'medium', 'high']:
                subset = [r for r in self.results if r.get('vol_level') == vl]
                if subset:
                    avg = sum(r['wr_s'] for r in subset)/len(subset)
                    wr80s = sum(1 for r in subset if r['wr_s']>=80)/len(subset)*100
                    print(f"    {vl:>6s}: {len(subset):>4d} 只, avgWR={avg:.1f}%, WR80={wr80s:.1f}%")
        
        # 保存
        self.save_results()
        
        # 创建WebUI可读的报告
        self.save_webui_report()
        
        print(f"\n{'='*70}")
    
    def save_results(self):
        """保存结果"""
        # 按WR排序
        sorted_results = sorted(self.results, key=lambda r: -r['wr_s'])
        
        data = {
            'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
            'total_stocks': self.total,
            'processed': self.processed,
            'with_signals': len(self.results),
            'no_signals': self.no_signal_count,
            'errors': self.error_count,
            'duration_min': round((time.time()-self.start_time)/60, 1),
        }
        
        if self.results:
            wr_s_list = [r['wr_s'] for r in self.results]
            data['median_wr'] = round(sorted(wr_s_list)[len(wr_s_list)//2], 1)
            data['avg_wr'] = round(sum(wr_s_list)/len(wr_s_list), 1)
            data['wr80_pct'] = round(sum(1 for r in self.results if r['wr_s']>=80)/len(self.results)*100, 1)
            data['wr100_pct'] = round(sum(1 for r in self.results if r['wr_s']==100)/len(self.results)*100, 1)
            data['total_signal_count'] = sum(r['n_s'] for r in self.results)
        
        # 汇总
        with open(OPT_DIR / 'scan_v4_summary.json', 'w') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        # 完整结果
        simplified = [{
            'code': r['code'],
            'name': r['name'],
            'wr_s': r['wr_s'],
            'n_s': r['n_s'],
            'pf_s': r.get('pf_s', 0),
            'vol': r.get('vol_level', '?'),
            'atr': r.get('atr_pct', 0),
        } for r in sorted_results]
        
        with open(OPT_DIR / 'scan_v4_results.json', 'w') as f:
            json.dump(simplified, f, indent=2, ensure_ascii=False)
        
        print(f"\n✅ 结果已保存:")
        print(f"   汇总: {OPT_DIR}/scan_v4_summary.json")
        print(f"   详情: {OPT_DIR}/scan_v4_results.json ({len(simplified)} 只有信号)")
    
    def save_webui_report(self):
        """保存WebUI可读报告"""
        lines = []
        lines.append('=' * 70)
        lines.append(f'  SMC V4 — 5000只全覆盖 最终报告')
        lines.append(f'  时间: {time.strftime("%Y-%m-%d %H:%M:%S")}')
        lines.append(f'  耗时: {(time.time()-self.start_time)/60:.1f}分钟')
        lines.append(f'  并行: {MAX_WORKERS} workers | Klines: 300')
        lines.append('=' * 70)
        
        lines.append(f'\n📊 覆盖:')
        lines.append(f'  总股票: {self.total}')
        lines.append(f'  有信号: {self.signal_count} ({self.signal_count/max(1,self.processed)*100:.1f}%)')
        lines.append(f'  无信号: {self.no_signal_count}')
        lines.append(f'  错误:   {self.error_count}')
        
        if self.results:
            wr = [r['wr_s'] for r in self.results]
            lines.append(f'\n📊 V4 strict 信号质量:')
            
            for lo, hi in [(0,20),(20,40),(40,60),(60,80),(80,90),(90,100)]:
                cnt = sum(1 for r in self.results if lo <= r['wr_s'] < hi)
                bar = '█' * int(cnt / len(self.results) * 50) if self.results else ''
                pct = cnt/len(self.results)*100
                lines.append(f'  WR {lo:>3d}-{hi:<3d}%: {cnt:>5d} ({pct:>5.1f}%) {bar}')
        
        with open(OPT_DIR / 'scan_v4_report.txt', 'w') as f:
            f.write('\n'.join(lines))
        
        # 打印
        print(f"\n✅ WebUI报告: {OPT_DIR}/scan_v4_report.txt")


if __name__ == '__main__':
    quick = '--quick' in sys.argv
    
    print(f"\n{'='*70}")
    print(f"  SMC V4 — {'5000只全覆盖 (快速)' if quick else '5000只全覆盖'} v2")
    print(f"  多线程: {MAX_WORKERS} workers")
    print(f"  缓存: {KLINE_CACHE}")
    print(f"{'='*70}")
    
    scanner = V4MassScanner(quick=quick)
    scanner.run()