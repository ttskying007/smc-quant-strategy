#!/usr/bin/env python3
"""Decrypt Chrome cookies using the secret service API."""
import json
import sqlite3
import os
import base64
import subprocess

# Try to get key from secret-tool
result = subprocess.run(
    ['secret-tool', 'search', '--all', 'application', 'chrome'],
    capture_output=True, text=True, timeout=10
)
print("=== secret-tool search ===")
print("stdout:", result.stdout[:500])
print("stderr:", result.stderr[:500])
print("rc:", result.returncode)

# Also try looking for the key with label
result2 = subprocess.run(
    ['secret-tool', 'lookup', 'application', 'chrome', 'label', 'Chrome Safe Storage'],
    capture_output=True, text=True, timeout=10
)
print("\n=== secret-tool lookup ===")
print("stdout:", result2.stdout[:200])
print("stderr:", result2.stderr[:200])

# Try specific attribute combos
result3 = subprocess.run(
    ['secret-tool', 'search', '--all', 'application', 'chrome', 'attribute', 'chrome-safe-storage'],
    capture_output=True, text=True, timeout=10
)
print("\n=== secret-tool search (alt) ===")
print("stdout:", result3.stdout[:500])
print("stderr:", result3.stderr[:500])
