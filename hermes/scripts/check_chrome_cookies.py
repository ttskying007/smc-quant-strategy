#!/usr/bin/env python3
import json
import sqlite3

# Check Local State
with open('/home/lei/.config/google-chrome/Local State') as f:
    ls = json.load(f)

oscrypt = ls.get('os_crypt', {})
print('os_crypt keys:', list(oscrypt.keys()))
for k, v in oscrypt.items():
    if isinstance(v, str) and len(v) > 50:
        print(f'  {k}: {v[:60]}...')
    else:
        print(f'  {k}: {v}')

# Check cookies DB
db_path = '/home/lei/.config/google-chrome/Default/Cookies'
conn = sqlite3.connect(db_path)
conn.text_factory = bytes
c = conn.cursor()

print('\n--- Schema ---')
c.execute('SELECT * FROM meta ORDER BY key')
for row in c.fetchall():
    print(row)

print('\n--- X.com cookies ---')
c.execute("SELECT host_key, name, hex(encrypted_value)[:80] FROM cookies WHERE host_key LIKE '%x.com' OR host_key LIKE '%twitter.com'")
for row in c.fetchall():
    host = row[0].decode()
    name = row[1].decode()
    print(f'{host}: {name} = {row[2][:80]}')

conn.close()
