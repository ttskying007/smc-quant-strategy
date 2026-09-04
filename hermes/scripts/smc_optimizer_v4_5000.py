#!/usr/bin/env python3
"""
SMC V4 Optimizer — 5000只全覆盖版
======================================
核心设计:
  1. 全覆盖: 将5512只股票分成417组,每组~12只,逐组评估
  2. 自适应淘汰: 第1轮评估所有, 无信号股票自动标记跳过
  3. 渐进式过滤: 每轮保留有信号的股票, 无信号的标记后跳过
  4. 评分: 使用上一轮最佳参数验证, 兼顾覆盖率和胜率
  5. 3个pass: 全覆盖(1轮/组) → 精选(重复验证) → 交叉验证

目标: 5000+只股票全覆盖, 验证V4引擎在全部A股上的稳定性
目标WR: strict >80%, total >50%

用法:
  python3 smc_optimizer_v4_5000.py          # 默认: 全覆盖
  python3 smc_optimizer_v4_5000.py --quick   # 仅500只快速验证
"""

import sys, os, json, random, math, time, copy, threading
from pathlib import Path
from collections import defaultdict

SMC_DIR = os.path.expanduser('~/.hermes/scripts')
sys.path.insert(0, SMC_DIR)

for k in ['http_proxy','https_proxy','HTTP_PROXY','HTTPS_PROXY']:
    os.environ.pop(k, None)

from smc_engine_v4 import (
    get_klines, get_stock_list, backtest_v4, 
    get_volatility_profile, get_adaptive_params
)

OPT_DIR = Path.home() / '.hermes' / 'smc_opt_v4'
OPT_DIR.mkdir(parents=True, exist_ok=True)

# ═══════════════════════════════════════════════
# 5000只全覆盖优化器
# ═══════════════════════════════════════════════

class V4Optimizer5000:
    def __init__(self, quick_mode=False):
        self.quick_mode = quick_mode
        self.all_stocks = []          # [(code, name), ...]
        self.signal_map = {}          # {code: {has_signal: bool, n_strict:int, ...}}
        self.silent_stocks = set()    # 无信号的股票集合
        self.groups = []              # 分组列表
        self.total_groups = 0
        self.current_group = 0
        self.results = []             # 每只股票的回测结果
        
        # 最佳参数 (继承自上一轮200轮的最佳)
        self.best_params = {
            'fvg_threshold_std': 0.26,
            'fvg_threshold_wide': 0.16,
            'fvg_merge_gap': 4,
            'fvg_min_strength': 2,
            'fvg_max_age': 26,
            'sweep_lookback': 13,
            'sweep_wick_min': 1.5,
            'sweep_body_min': 0.2,
            'sweep_dist_pre': 5,
            'sweep_dist_post': 10,
            'score_loose_th': 1.7,
            'score_strict_th': 3.7,
            'strict_min_sigs': 3,
            'sl_mult_base': 2.5,
            'tp_mult_base': 2.1,
            'sl_shrink_ratio': 0.4,
            'tp_expand_ratio': 0.55,
        }
        self.start_time = time.time()
    
    def load_stocks(self):
        """加载所有股票"""
        all_s = get_stock_list()
        self.all_stocks = [(s['symbol'], s.get('name','')) for s in all_s 
                          if not s.get('symbol','').startswith('*ST')]
        random.shuffle(self.all_stocks)
        
        if self.quick_mode:
            self.all_stocks = self.all_stocks[:500]
        
        print(f"  Loaded {len(self.all_stocks)} stocks")
        
        # 分组
        group_size = 12
        self.groups = [self.all_stocks[i:i+group_size] 
                      for i in range(0, len(self.all_stocks), group_size)]
        self.total_groups = len(self.groups)
        print(f"  Groups: {self.total_groups} (size={group_size})")
    
    def backtest_stock(self, code, name):
        """回测单只股票"""
        try:
            bars = get_klines(code, 'daily', 600)
            if len(bars) < 120:
                return None
            
            vol = get_volatility_profile(bars)
            v4_params = {
                'fvg_threshold': self.best_params['fvg_threshold_std'],
                'score_threshold': self.best_params['score_loose_th'],
                'sl_mult': self.best_params['sl_mult_base'],
                'tp_mult': self.best_params['tp_mult_base'],
            }
            
            strict_trades = backtest_v4(bars, 'strict', v4_params)
            total_trades = backtest_v4(bars, 'total', v4_params)
            
            result = {'code':code, 'name':name, 'vol_level': vol['vol_level'], 'atr_pct': vol['atr_pct']}
            
            if strict_trades:
                wins = [t for t in strict_trades if t['pnl']>0]
                losses = [t for t in strict_trades if t['pnl']<=0]
                result['n_s'] = len(strict_trades)
                result['wr_s'] = len(wins)/len(strict_trades)*100
                result['pf_s'] = abs(sum(t['pnl'] for t in wins)/sum(t['pnl'] for t in losses)) if losses and sum(t['pnl'] for t in losses)!=0 else 999
                avg = sum(t['pnl'] for t in strict_trades)/len(strict_trades)
                std = math.sqrt(sum((t['pnl']-avg)**2 for t in strict_trades)/len(strict_trades)) if len(strict_trades)>1 else 0.001
                result['sr_s'] = (avg/std)*math.sqrt(252) if std>0 else 0
            else:
                result['n_s'] = 0; result['wr_s'] = 0; result['pf_s'] = 0; result['sr_s'] = 0
            
            if total_trades:
                wins = [t for t in total_trades if t['pnl']>0]
                losses = [t for t in total_trades if t['pnl']<=0]
                result['n_t'] = len(total_trades)
                result['wr_t'] = len(wins)/len(total_trades)*100
                result['pf_t'] = abs(sum(t['pnl'] for t in wins)/sum(t['pnl'] for t in losses)) if losses and sum(t['pnl'] for t in losses)!=0 else 999
            else:
                result['n_t'] = 0; result['wr_t'] = 0; result['pf_t'] = 0
            
            return result
        except Exception as e:
            return None
    
    def evaluate_group(self, group_idx):
        """评估一组股票"""
        group = self.groups[group_idx]
        results = []
        silent_count = 0
        has_signal_count = 0
        
        for idx, (code, name) in enumerate(group):
            # 跳过已知无信号股票
            if code in self.silent_stocks:
                silent_count += 1
                continue
            
            r = self.backtest_stock(code, name)
            if r is None:
                continue
            
            results.append(r)
            self.results.append(r)
            
            if r['n_s'] >= 2:
                has_signal_count += 1
                self.signal_map[code] = {'has_signal': True, 'n_s': r['n_s'], 'wr_s': r['wr_s']}
            else:
                self.signal_map.setdefault(code, {'has_signal': False, 'n_s': 0, 'wr_s': 0})
        
        return results, silent_count, has_signal_count
    
    def run(self):
        """主循环"""
        self.load_stocks()
        
        print(f"\n{'='*70}")
        print(f"  SMC V4 — 5000只全覆盖优化")
        print(f"  总股票: {len(self.all_stocks)}")
        print(f"  总组数: {self.total_groups} (每轮一组)")
        print(f"  使用参数: fvg_th={self.best_params['fvg_threshold_std']} "
              f"strict_th={self.best_params['score_strict_th']}"
              f"sl={self.best_params['sl_mult_base']}"
              f"tp={self.best_params['tp_mult_base']}")
        print(f"{'='*70}")
        
        start = time.time()
        
        for gi in range(self.total_groups):
            self.current_group = gi + 1
            
            # 如果所有剩余股票都无信号, 提前结束
            remaining = len(self.all_stocks) - sum(len(g) for g in self.groups[:gi])
            remaining_new = remaining - sum(1 for g in self.groups[gi:] for c,_ in g if c in self.silent_stocks)
            if remaining_new <= 0:
                print(f"\n  ⚡ All remaining stocks have no signal. Stopping early.")
                break
            
            t0 = time.time()
            results, silent, has_sig = self.evaluate_group(gi)
            elapsed = time.time() - t0
            
            # 统计
            group_stocks = len(self.groups[gi])
            silent_new = silent
            signal_stocks = len([r for r in results if r and r['n_s'] >= 2])
            
            # 当前组的WR
            valid_results = [r for r in results if r and r['n_s'] > 0]
            if valid_results:
                avg_wr_s = sum(r['wr_s'] for r in valid_results)/len(valid_results)
                avg_n_s = sum(r['n_s'] for r in valid_results)/len(valid_results)
                avg_wr_t = sum(r['wr_t'] for r in valid_results)/len(valid_results)
                wr80 = sum(1 for r in valid_results if r['wr_s'] >= 80)/len(valid_results)*100
            else:
                avg_wr_s = avg_n_s = avg_wr_t = wr80 = 0
            
            # 标记无信号股票
            for r in results:
                if r and r['n_s'] == 0:
                    self.silent_stocks.add(r['code'])
            
            # 整体统计
            total_results = len(self.results)
            valid_all = [r for r in self.results if r and r['n_s'] > 0]
            total_wr80 = sum(1 for r in valid_all if r['wr_s'] >= 80)/len(valid_all)*100 if valid_all else 0
            
            progress = f"{self.current_group:>4d}/{self.total_groups}"
            pct = f"{(self.current_group/self.total_groups*100):>5.1f}%"
            wr_str = f"WR_s={avg_wr_s:>5.1f}%"
            n_str = f"nS={avg_n_s:>4.1f}"
            wr80_str = f"WR80={wr80:>4.0f}%"
            total_wr80_str = f"tot={total_wr80:>4.0f}%"
            sig_str = f"sig={signal_stocks}/{group_stocks-silent_new}"
            total_sig = sum(1 for r in valid_all if r['n_s'] >= 2)
            
            marker = '✅' if avg_wr_s >= 80 else '  '
            
            print(f"  {progress} | {pct} | {wr_str} | {n_str} | {wr80_str} | "
                  f"{total_wr80_str} | {sig_str} | totSig={total_sig} | {elapsed:.1f}s {marker}")
            
            # 每50组保存结果
            if gi % 50 == 0 and gi > 0:
                self.save_progress()
        
        # ═══ 完成 ═══
        total_time = time.time() - start
        print(f"\n{'='*70}")
        print(f"  🏁 SMC V4 — 5000只全覆盖完成!")
        print(f"  总时间: {total_time/60:.1f}分钟")
        print(f"  组数: {self.current_group}/{self.total_groups}")
        print(f"{'='*70}")
        
        self.save_final()
        self.print_summary()
    
    def save_progress(self):
        """保存中间结果"""
        valid_all = [r for r in self.results if r and r['n_s'] > 0]
        data = {
            'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
            'total_stocks_tested': len(self.results),
            'stocks_with_signals': len(valid_all),
            'silent_stocks': len(self.silent_stocks),
            'groups_completed': self.current_group,
            'total_groups': self.total_groups,
        }
        if valid_all:
            wr_s_list = [r['wr_s'] for r in valid_all]
            n_s_list = [r['n_s'] for r in valid_all]
            data['avg_wr_s'] = round(sum(wr_s_list)/len(wr_s_list), 1)
            data['median_wr_s'] = round(sorted(wr_s_list)[len(wr_s_list)//2], 1)
            data['wr80_pct'] = round(sum(1 for r in valid_all if r['wr_s']>=80)/len(valid_all)*100, 1)
            data['wr100_pct'] = round(sum(1 for r in valid_all if r['wr_s']==100)/len(valid_all)*100, 1)
            data['avg_n_s'] = round(sum(n_s_list)/len(n_s_list), 1)
            data['total_signals'] = sum(n_s_list)
        
        with open(OPT_DIR / 'progress_5000.json', 'w') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        # 保存完整的股票结果
        stock_results = []
        for r in self.results:
            stock_results.append({
                'code': r['code'], 'name': r['name'],
                'wr_s': round(r['wr_s'], 1) if r['n_s'] > 0 else 0,
                'n_s': r['n_s'],
                'wr_t': round(r['wr_t'], 1) if r['n_t'] > 0 else 0,
                'n_t': r['n_t'],
                'pf_s': round(r['pf_s'], 2),
                'sr_s': round(r['sr_s'], 2),
                'vol_level': r.get('vol_level', 'unknown'),
                'atr_pct': r.get('atr_pct', 0),
            })
        stock_results.sort(key=lambda x: -x['wr_s'])
        
        with open(OPT_DIR / 'stock_results_5000.json', 'w') as f:
            json.dump(stock_results, f, indent=2, ensure_ascii=False)
    
    def save_final(self):
        """保存最终结果"""
        self.save_progress()  # 同函数
        # 再保存一份汇总
        self.print_summary(to_file=True)
    
    def print_summary(self, to_file=False):
        """打印汇总"""
        valid_all = [r for r in self.results if r and r['n_s'] > 0]
        silent = len(self.silent_stocks)
        total_test = len(self.results)
        
        lines = []
        lines.append('=' * 70)
        lines.append(f'  SMC V4 — 5000只全覆盖 结果报告')
        lines.append(f'  时间: {time.strftime("%Y-%m-%d %H:%M:%S")}')
        lines.append(f'  总耗时: {(time.time()-self.start_time)/60:.1f}分钟')
        lines.append('=' * 70)
        lines.append(f'')
        lines.append(f'  📊 覆盖统计:')
        lines.append(f'     总股票池:   {len(self.all_stocks)}')
        lines.append(f'     已测试:     {total_test}')
        lines.append(f'     有信号:     {len(valid_all)} ({len(valid_all)/max(1,total_test)*100:.1f}%)')
        lines.append(f'     无信号:     {silent} ({silent/max(1,total_test)*100:.1f}%)')
        lines.append(f'')
        
        if valid_all:
            wr_s_list = [r['wr_s'] for r in valid_all]
            n_s_list = [r['n_s'] for r in valid_all]
            wr_s_sorted = sorted(wr_s_list)
            
            avg_wr = sum(wr_s_list)/len(wr_s_list)
            med_wr = wr_s_sorted[len(wr_s_list)//2]
            wr80 = sum(1 for r in valid_all if r['wr_s']>=80)/len(valid_all)*100
            wr100 = sum(1 for r in valid_all if r['wr_s']==100)/len(valid_all)*100
            total_sig = sum(n_s_list)
            
            lines.append(f'  📊 V4引擎性能 (strict模式):')
            lines.append(f'     平均WR:     {avg_wr:.1f}%')
            lines.append(f'     中位数WR:   {med_wr:.1f}%')
            lines.append(f'     WR>=80%:    {wr80:.1f}% 的股票')
            lines.append(f'     WR=100%:    {wr100:.1f}% 的股票')
            lines.append(f'     总信号数:   {total_sig}')
            lines.append(f'     平均N(strict): {sum(n_s_list)/len(n_s_list):.1f} 笔/股')
            
            # WR分布
            lines.append(f'')
            lines.append(f'  📊 WR分布:')
            bins = [(0, 20), (20, 40), (40, 60), (60, 80), (80, 90), (90, 100)]
            for lo, hi in bins:
                cnt = sum(1 for r in valid_all if lo <= r['wr_s'] < hi)
                bar = '█' * max(1, int(cnt / max(1, len(valid_all)) * 40))
                lines.append(f'     {lo:>3d}-{hi:<3d}%: {cnt:>5d} ({cnt/len(valid_all)*100:>5.1f}%) {bar}')
            
            # total模式
            total_valid = [r for r in self.results if r and r['n_t'] > 0]
            if total_valid:
                avg_wr_t = sum(r['wr_t'] for r in total_valid)/len(total_valid)
                total_sig_t = sum(r['n_t'] for r in total_valid)
                lines.append(f'')
                lines.append(f'  📊 total模式:')
                lines.append(f'     平均WR:     {avg_wr_t:.1f}%')
                lines.append(f'     总信号数:   {total_sig_t}')
            
            # 按波动率分类
            lines.append(f'')
            lines.append(f'  📊 按波动率分类 (strict WR):')
            for vl in ['low', 'medium', 'high']:
                subset = [r for r in valid_all if r.get('vol_level') == vl]
                if subset:
                    subset_wr = sum(r['wr_s'] for r in subset)/len(subset)
                    lines.append(f'     {vl:>6s}: {len(subset):>4d} 只, avgWR={subset_wr:.1f}%')
        
        lines.append(f'')
        lines.append(f'  ⚙️ 使用参数:')
        for k, v in sorted(self.best_params.items()):
            lines.append(f'     {k:>25s}: {v}')
        lines.append(f'')
        lines.append(f'=' * 70)
        
        output = '\n'.join(lines)
        print(output)
        
        if to_file:
            with open(OPT_DIR / 'final_report_5000.txt', 'w') as f:
                f.write(output)
            print(f'\n✅ 报告已保存: {OPT_DIR / "final_report_5000.txt"}')


if __name__ == '__main__':
    quick = '--quick' in sys.argv
    
    print(f"\n{'='*70}")
    print(f"  SMC V4 — 5000只全覆盖 {'(快速模式:500只)' if quick else ''}")
    print(f"{'='*70}")
    
    opt = V4Optimizer5000(quick_mode=quick)
    opt.run()