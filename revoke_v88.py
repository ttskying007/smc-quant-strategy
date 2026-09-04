# -*- coding: utf-8 -*-
"""Task 1: revoke V88 production label.
- ACTIVE_VERSION driven by production registry (R16), file-existence inference abolished.
- EMPTY_BOOK sentinel routes trade/pick/metrics to empty.
- Backup original file first.
"""
import io, os, re, shutil, sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
P = r"E:\test\smc_project\hermes\scripts\smc_unified.py"
bak = P + ".bak_v88revoke"
shutil.copyfile(P, bak)
txt = open(P, encoding="utf-8", errors="replace").read()

# ---- 1. ACTIVE_VERSION block -> registry-driven ----
start_marker = "# Active version \u2014 production defaults to latest validated SMC version."
i0 = txt.find(start_marker)
i1 = txt.find("else 'V27')", i0)
if i0 < 0 or i1 < 0:
    print("MARKER NOT FOUND for ACTIVE_VERSION"); sys.exit(1)
i1 = i1 + len("else 'V27')")
new_block = '''# FIX(2026-08-17): \u751f\u4ea7\u7248\u672c\u53ea\u7531 production registry \u51b3\u5b9a\uff08R16\uff09\u3002
# \u6587\u4ef6\u5b58\u5728\u6027\u63a8\u65ad\u5df2\u5e9f\u9664\u3002V88 \u56e0\u524d\u89c6\u504f\u5dee\u88ab\u6b63\u5f0f\u5426\u51b3
# \uff08REJECTED_LOOKAHEAD\uff0c\u8bc1\u636e\uff1aV88\u91cd\u9a8c\u62a5\u544a.md\uff09\u3002EMPTY_BOOK \u65f6\u4e3a\u54e8\u5175\u503c\u3002
try:
    import json as _json_mod
    _REGISTRY_RAW = _json_mod.loads(Path('/root/.hermes/smc_monitor/production_registry.json').read_text())
except Exception:
    _REGISTRY_RAW = {}
ACTIVE_VERSION = str(_REGISTRY_RAW.get('production_strategy') or 'EMPTY_BOOK')
REJECTED_VERSIONS = {
    'V88': 'REJECTED_LOOKAHEAD: TP target used future-20-bar highs; reverify WR 80%->41.6%, PF 6.2->1.10 (V88重验报告.md)',
    'V86': 'REJECTED_LOOKAHEAD: same future-bar liquidity lineage as V88',
    'V85': 'REJECTED_LOOKAHEAD: signal layer feeds V86/V88 future-bar liquidity',
}
'''
txt = txt[:i0] + new_block + txt[i1:]

# ---- 2. ACTIVE_TRADE_FILE / ACTIVE_PICK_FILE: EMPTY_BOOK -> None ----
for var in ("ACTIVE_TRADE_FILE", "ACTIVE_PICK_FILE"):
    pat = re.compile(rf"^{var} = \(Path\('/root/\.hermes/smc_opt_v88_production_contract/v88_", re.M)
    m = pat.search(txt)
    if not m:
        print(f"{var} v88 branch not found"); continue
    prefix = f"{var} = (Path("
    new_prefix = f"{var} = (None if ACTIVE_VERSION == 'EMPTY_BOOK' else Path("
    txt = txt[:m.start()] + new_prefix + txt[m.start() + len(prefix):]
    print(f"{var}: EMPTY_BOOK branch inserted")

# ---- 3. reload_metrics: EMPTY_BOOK -> {} ----
i = txt.find("def reload_metrics():")
if i >= 0:
    j = txt.find("mp = paths.get('metrics')", i)
    if j > 0:
        ins = "    if ACTIVE_VERSION == 'EMPTY_BOOK':\n        return {}\n"
        txt = txt[:j] + ins + txt[j:]

# ---- 4. _promoted_contract_dir: skip rejected versions (V88/V185...) ----
# (frontend label already returns EMPTY_BOOK; leave promoted_contract_dir for historical audits)

open(P, "w", encoding="utf-8").write(txt)
print("written; backup:", bak)
