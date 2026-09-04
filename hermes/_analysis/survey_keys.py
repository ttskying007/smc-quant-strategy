# -*- coding: utf-8 -*-
"""Survey top-level keys across all smc_opt_v*/report*.json files."""
import json, os, glob, collections

ROOT = r"E:\test\smc_project\hermes"
MAXSIZE = 10 * 1024 * 1024

files = []
for d in sorted(glob.glob(os.path.join(ROOT, "smc_opt_v*"))):
    if not os.path.isdir(d):
        continue
    for f in sorted(glob.glob(os.path.join(d, "*.json"))):
        bn = os.path.basename(f).lower()
        if "report" not in bn and "gate" not in bn and "summary" not in bn and "matrix" not in bn:
            continue
        if os.path.getsize(f) > MAXSIZE:
            continue
        files.append(f)

print("JSON report-like files:", len(files))
keycount = collections.Counter()
samples = {}
for f in files:
    try:
        with open(f, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception as e:
        print("PARSE_FAIL", f, e)
        continue
    if not isinstance(data, dict):
        print("NOT_DICT", f, type(data))
        continue
    for k in data.keys():
        keycount[k] += 1
        samples.setdefault(k, f)

for k, c in keycount.most_common():
    print(f"{c:4d}  {k}   <- {os.path.basename(samples[k])}")
