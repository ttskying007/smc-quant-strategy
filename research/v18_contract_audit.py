# -*- coding: utf-8 -*-
"""R9 audit: v18 contract text == code (VWAP 5%, FVG, ADX 20, holds 15/20)."""
import io, os, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

checks = [
    ("VWAP 5%", "0.05", r"E:\test\smc_project\research\combo_v18_run.py"),
    ("FVG 12bar", "i - 12", r"E:\test\smc_project\research\combo_v18_run.py"),
    ("ADX 20", "adx < 20", r"E:\test\smc_project\research\combo_v18_run.py"),
    ("hold 15", "15", r"E:\test\smc_project\research\combo_v18_run.py"),
    ("hold 20 deep", "20 if deep else 15", r"E:\test\smc_project\research\combo_v18_run.py"),
    ("r20 0.15", "0 <= r20 < 0.15", r"E:\test\smc_project\research\combo_v18_run.py"),
]
for label, pat, path in checks:
    txt = open(path, encoding="utf-8", errors="replace").read()
    print(f"  [{'OK' if pat in txt else 'MISS'}] {label}: '{pat}' in {os.path.basename(path)}")
