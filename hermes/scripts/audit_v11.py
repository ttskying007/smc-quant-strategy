#!/usr/bin/env python3
"""审计V11所有代码Bug"""
import ast, sys
from pathlib import Path

v11_dir = Path('/root/.hermes/scripts/v11')
files = sorted(v11_dir.glob('*.py'))

# Check: which functions reference Signal as dict vs dataclass
print("=" * 60)
print("V11 代码审计 — Signal 对象访问一致性检查")
print("=" * 60)

for f in files:
    code = f.read_text()
    lines = code.split('\n')
    
    # Find issues
    issues = []
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        
        # Skip comments and strings
        if stripped.startswith('#') or stripped.startswith('"') or stripped.startswith("'"):
            continue
            
        # Check for Signal dataclass field access via [] that should be .
        # Fields: type, idx, direction, price, timeframe, strength, confidence, upper, lower
        # confirmed_at, expired_at, is_active, grade, trend_aligned, volume_ratio, metadata
        signal_fields = ['type', 'idx', 'direction', 'price', 'strength', 'confidence',
                        'upper', 'lower', 'confirmed_at', 'expired_at', 'is_active',
                        'grade', 'trend_aligned', 'volume_ratio', 'metadata']
        
        for field in signal_fields:
            pattern = f"['{field}']"
            if pattern in stripped and 'sig' in stripped.lower() or 'signal' in stripped.lower():
                # Only flag if it's accessing a Signal object, not a plain dict
                if 'sig[' in stripped or 'signal[' in stripped:
                    issues.append((i, f"Dict access '{pattern}' on sig"))
        
        # Check for .to_dict() calls
        if '.to_dict()' in stripped and stripped.strip().startswith('#'):
            issues.append((i, "to_dict() in comment?"))

    if issues:
        print(f"\n  {f.name}:")
        for lineno, msg in issues[:20]:
            context = lines[lineno-1].strip()[:80]
            print(f"    L{lineno}: {msg}")
            print(f"      -> {context}")

print("\n" + "=" * 60)
print("CHOCH 过度检测分析")
print("=" * 60)

sig_file = v11_dir / 'signals_v11.py'
sig_code = sig_file.read_text()
choch_start = sig_code.find("def detect_choch_v11")
choch_section = sig_code[choch_start:choch_start + 4000]
print(choch_section[:2000])

print("\n---")
print("BPR 检查: fvg_signals 参数是 dict 还是 Signal?")
bpr_def = sig_code.find("def detect_bpr_v11")
print(sig_code[bpr_def:bpr_def+500])
