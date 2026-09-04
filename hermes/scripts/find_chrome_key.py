#!/usr/bin/env python3
"""Search for Chrome encryption key files."""
import os
import json

profile_dir = '/home/lei/.config/google-chrome/Default'

# List files in profile dir that might contain key info
print("=== Files in profile (filtered) ===")
for f in sorted(os.listdir(profile_dir)):
    f_lower = f.lower()
    if any(k in f_lower for k in ['key', 'crypt', 'secret', 'token', 'local', 'state']):
        fpath = os.path.join(profile_dir, f)
        size = os.path.getsize(fpath)
        print(f"  {f} ({size} bytes)")

# Check Local Storage for encryption-related data  
ls_dir = os.path.join(profile_dir, 'Local Storage', 'leveldb')
if os.path.exists(ls_dir):
    print(f"\n=== Local Storage leveldb exists ===")
    for f in sorted(os.listdir(ls_dir))[:10]:
        print(f"  {f}")

# Check for any .key file
print(f"\n=== Searching for .key files ===")
import subprocess
r = subprocess.run(['find', '/home/lei/.config/google-chrome', '-name', '*.key'], capture_output=True, text=True, timeout=5)
for line in r.stdout.strip().split('\n'):
    if line:
        print(f"  {line}")

# Check if there's specific Chrome data directory
r2 = subprocess.run(['find', '/home/lei/.local/share/', '-name', '*chrome*', '-o', '-name', '*chromium*'], capture_output=True, text=True, timeout=5)
out = r2.stdout.strip()
if out:
    print(f"\n=== Chrome data dirs ===")
    for line in out.split('\n'):
        print(f"  {line}")

# Let's try the simplest thing: decrypt with an empty key (some Chrome versions use this as fallback)
print(f"\n=== Trying to find how Chrome encrypts cookies ===")
# The encrypted values start with 'v11' - standard AES-256-GCM
# Without keyring, Chrome might store the key in a file we haven't found
# Let's check the leveldb for the key
for root, dirs, files in os.walk(os.path.join(profile_dir, 'Local Storage')):
    for f in files:
        fpath = os.path.join(root, f)
        try:
            with open(fpath, 'rb') as fh:
                data = fh.read()
                # Look for base64-like strings that are 44 chars (32 bytes in base64 = 44 chars)
                import re
                for match in re.finditer(rb'[A-Za-z0-9+/=]{40,50}', data):
                    candidate = match.group().decode('ascii', errors='replace')
                    try:
                        decoded = __import__('base64').b64decode(candidate)
                        if len(decoded) == 32:
                            print(f"  POTENTIAL KEY in {f}: {candidate}")
                    except:
                        pass
        except:
            pass
