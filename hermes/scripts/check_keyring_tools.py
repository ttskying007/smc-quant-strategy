#!/usr/bin/env python3
import subprocess

# Check what keyring tools are available
for cmd in ['secret-tool', 'gnome-keyring', 'python3-keyring']:
    r = subprocess.run(['which', cmd], capture_output=True, text=True)
    print(f'{cmd}: {r.stdout.strip() or "not found"}')

# Check pip for keyring
r = subprocess.run(['pip3', 'list', '--format=columns'], capture_output=True, text=True)
lines = r.stdout.lower().split('\n')
for line in lines:
    if 'keyring' in line or 'secret' in line or 'crypt' in line:
        print(f'pip: {line.strip()}')

# Check gi
r = subprocess.run(['python3', '-c', 'import gi; gi.require_version("Secret", "1"); from gi.repository import Secret; print("gi.Secret OK")'], capture_output=True, text=True)
print(f'gi.Secret: {r.stdout.strip() or r.stderr.strip() or "FAILED"}')
