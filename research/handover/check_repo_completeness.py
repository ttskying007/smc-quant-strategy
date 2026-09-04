# -*- coding: utf-8 -*-
"""严格对比工作区 vs git 跟踪：找出真实未跟踪/未忽略的文件（处理中文转义）"""
import os, subprocess, sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

ROOT = r"E:\test\smc_project"
os.chdir(ROOT)

def run(args):
    r = subprocess.run(args, capture_output=True, text=True, encoding='utf-8', errors='replace', cwd=ROOT)
    return r.stdout

# git 跟踪清单（用 -z 避免转义歧义）
tracked = set()
raw = subprocess.run(['git', 'ls-files', '-z'], capture_output=True, cwd=ROOT)
tracked = set(raw.stdout.decode('utf-8', errors='replace').split('\0')) - {''}

SKIP_SUFFIX = {'.pyc', '.db', '.csv', '.tar.gz', '.gz', '.log', '.bak'}
SKIP_DIR = {'__pycache__', '.git', '.tmpdir', 'node_modules', 'crawl_data', 'kline_cache',
            'kline_cache_tencent', 'kline_cache_15min', 'kline_cache_60min', 'kline_cache_weekly',
            'kline_cache_etf', 'kline_cache_full', 'smc_audit', 'downloads', '.gitnexus', '.hermes'}

missing_code = []   # 未跟踪的代码/文档（应入库）
missing_data = []   # 未跟踪的数据（可忽略）
for dirpath, dirnames, filenames in os.walk(ROOT):
    dirnames[:] = [d for d in dirnames if d not in SKIP_DIR and not d.startswith('smc_opt_')]
    for fn in filenames:
        full = os.path.join(dirpath, fn)
        rel = os.path.relpath(full, ROOT).replace(os.sep, '/')
        if rel in tracked:
            continue
        is_data = (fn.endswith(('.csv', '.db', '.pyc', '.tar.gz', '.gz', '.log', '.bak'))
                   or fn in ('paper_ledger.json', 'selection_result.json', 'production_registry.json',
                             'run_status.json', 'combo_dashboard.json', 'current_scanner_result.json',
                             'realtime_log.json', 'positions.json', 'trade_ledger.json'))
        (missing_data if is_data else missing_code).append(rel)

print(f"=== 未跟踪代码/文档（应入库，{len(missing_code)}）===")
for p in sorted(missing_code):
    print("  " + p)
print(f"\n=== 未跟踪数据（忽略，{len(missing_data)}）===")
for p in sorted(missing_data)[:40]:
    print("  " + p)
if len(missing_data) > 40:
    print(f"  ... 共 {len(missing_data)} 个数据文件")
