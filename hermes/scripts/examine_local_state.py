#!/usr/bin/env python3
"""Examine Chrome's Local State for encryption key."""
import json

with open('/home/lei/.config/google-chrome/Local State') as f:
    data = json.load(f)

# Show all os_crypt keys
oscrypt = data.get('os_crypt', {})
print("=== os_crypt ===")
for k, v in oscrypt.items():
    if isinstance(v, dict):
        print(f"{k}: dict with keys: {list(v.keys())}")
    elif isinstance(v, str) and len(v) > 100:
        print(f"{k}: {v[:80]}...")
    elif isinstance(v, str) and 'key' in k.lower():
        print(f"{k}: {v}")
    else:
        print(f"{k}: {v}")

# Check for any other suspicious keys
print("\n=== Top-level keys matching 'key' or 'crypt' ===")
for k in data.keys():
    if 'key' in k.lower() or 'crypt' in k.lower() or 'secret' in k.lower():
        v = data[k]
        if isinstance(v, str) and len(v) > 50:
            print(f"{k}: {v[:80]}...")
        else:
            print(f"{k}: {v}")

# Check for any other chrome storage locations
print("\n=== Checking for user data encryption key ===")
import os
key_paths = [
    os.path.expanduser('~/.config/google-chrome/Default/Login Data'),
    os.path.expanduser('~/.config/google-chrome/Default/Login Data For Account'),
]
for p in key_paths:
    if os.path.exists(p):
        print(f"Found: {p}")

# Check for Chrome version info
print(f"\n=== Chrome profile version ===")
last_version = data.get('last_version', 'unknown')
print(f"last_version: {last_version}")

# Check profile info
print(f"\n=== Profile info ===")
if 'profile' in data:
    print(json.dumps(data['profile'], indent=2)[:500])

# Check if there are any other Chrome-related keyring files
print(f"\n=== Keyring files ===")
kr_path = os.path.expanduser('~/.local/share/keyrings/')
if os.path.exists(kr_path):
    for f in os.listdir(kr_path):
        print(f"  {f}")
