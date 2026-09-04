#!/usr/bin/env python3
"""Decrypt Chrome cookies using libsecret API."""
import json
import sqlite3
import base64
import gi
gi.require_version('Secret', '1')
from gi.repository import Secret

# Step 1: Get encryption key from libsecret
schema = Secret.Schema(
    "chrome_libsecret_os_crypt_password_v2",
    Secret.SchemaFlags.NONE,
    [("application", Secret.SchemaAttributeType.STRING)]
)

attributes = {"application": "chrome"}
print("Searching keyring for Chrome encryption key...")
passwords = Secret.password_search_sync(schema, attributes, Secret.SearchFlags.UNLOCK)
print(f"Found {len(passwords)} entries")

encryption_key = None
for pw in passwords:
    if hasattr(pw, 'get_secret_sync'):
        secret = pw.get_secret_sync()
        if secret and secret.get_text():
            try:
                key_bytes = base64.b64decode(secret.get_text().strip())
                print(f"Decoded key: {len(key_bytes)} bytes")
                if len(key_bytes) == 32:
                    encryption_key = key_bytes
                    print("Got 32-byte AES-256 key!")
                    break
            except Exception as e:
                print(f"Failed to decode key: {e}")

if not encryption_key:
    print("Trying alternative search...")
    # Try with different attributes
    result2 = Secret.password_search_sync(
        Secret.Schema(
            "chrome_libsecret_os_crypt_password",
            Secret.SchemaFlags.NONE,
            [("application", Secret.SchemaAttributeType.STRING)]
        ),
        {"application": "chrome"},
        Secret.SearchFlags.UNLOCK
    )
    print(f"Found {len(result2)} entries (v1 schema)")
    
    for pw in result2:
        print(f"  Entry type: {type(pw).__name__}")
        try:
            # Try different ways to get the value
            if hasattr(pw, 'get_secret_sync'):
                s = pw.get_secret_sync()
                if s:
                    text = s.get_text()
                    print(f"  Secret text: {text[:50] if text else 'None'}")
        except Exception as e:
            print(f"  Error: {e}")

if not encryption_key:
    print("\nTrying with all attributes listed...")
    # Some versions use attribute 'application'='chrome' and store key in different format
    # Let's enumerate all secrets
    service = Secret.Service.get_sync(Secret.ServiceFlags.OPEN_SESSION)
    items = service.collection_get_sync('default')
    if items:
        for item in items.get_items():
            attrs = item.get_attributes()
            print(f"  Item: {item.get_label()} :: {attrs}")

if encryption_key is None:
    print("\nERROR: Could not find Chrome encryption key")
    exit(1)

# Step 2: Read and decrypt cookies
db_path = '/home/lei/.config/google-chrome/Default/Cookies'
# Copy first to avoid locking issues
import shutil
shutil.copy2(db_path, '/tmp/chrome_cookies_copy')

conn = sqlite3.connect('/tmp/chrome_cookies_copy')
conn.text_factory = bytes
cursor = conn.cursor()

cursor.execute("""
    SELECT host_key, name, encrypted_value, is_secure, is_httponly
    FROM cookies 
    WHERE (host_key LIKE '%x.com' OR host_key LIKE '%twitter.com')
    AND name IN ('auth_token', 'ct0', 'twid', 'guest_id', 'kdt')
""")

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

results = {}
for host, name, enc_val, secure, httponly in cursor.fetchall():
    name_str = name.decode('utf-8')
    host_str = host.decode('utf-8')
    
    # Decrypt Chrome v11 format
    if enc_val.startswith(b'v11'):
        # v11(3) + nonce(12) + ciphertext + tag(16)
        nonce = enc_val[3:15]
        ciphertext_and_tag = enc_val[15:]
        try:
            aesgcm = AESGCM(encryption_key)
            decrypted = aesgcm.decrypt(nonce, ciphertext_and_tag, None)
            value = decrypted.decode('utf-8')
            results[name_str] = value
            print(f"  {name_str} = {value[:30]}... (from {host_str})")
        except Exception as e:
            print(f"  {name_str}: DECRYPT FAILED: {e}")
    else:
        print(f"  {name_str}: UNKNOWN FORMAT: {enc_val[:20].hex()}")

conn.close()

# Step 3: Save to JSON
output_path = '/root/.hermes/x_cookies_decrypted.json'
with open(output_path, 'w') as f:
    json.dump(results, f, indent=2)
print(f"\nSaved {len(results)} cookies to {output_path}")

# Additional: also get full cookie list for httpx
print("\n--- All X/Twitter cookies ---")
for k, v in results.items():
    print(f"  {k}={v[:50]}{'...' if len(v)>50 else ''}")
