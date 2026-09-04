#!/usr/bin/env python3
"""Fix v14_viewer.py render function - remove extra brace and correct order"""
import os, shutil

# Clear cache
cache_dir = '/root/.hermes/scripts/__pycache__'
for f in os.listdir(cache_dir):
    if 'v14_viewer' in f:
        os.remove(os.path.join(cache_dir, f))
        print(f"Removed {f}")

# Read the file
with open('/root/.hermes/scripts/v14_viewer.py') as f:
    content = f.read()

# The problematic line - the render function
# Old ending: `})}}]})};}`  (extra `}` before `]`)
# New ending: `})}])};}`    (correct: close chain then array then setOption arg)

old = '})}}]})'
new = '})}])})'
count = content.count(old)
print(f"Found {count} occurrences of old pattern")

if count > 0:
    content = content.replace(old, new)
    with open('/root/.hermes/scripts/v14_viewer.py', 'w') as f:
        f.write(content)
    print("Fixed!")
else:
    print("Pattern not found. Checking actual ending...")
    # Find the render function
    idx = content.find('function render')
    end_idx = content.find('var dom=document', idx)
    render_func = content[idx:end_idx]
    print(f"Render func ending: ...{render_func[-60:]}...")
