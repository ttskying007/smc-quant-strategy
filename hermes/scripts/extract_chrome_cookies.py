#!/usr/bin/env python3
"""Extract X.com cookies from Chrome's encrypted cookie database."""
import json
import sqlite3
import os
import base64
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

CHROME_PATH = os.path.expanduser("/home/lei/.config/google-chrome")

def get_encryption_key():
    """Get the Chrome encryption key from Local State."""
    local_state_path = os.path.join(CHROME_PATH, "Local State")
    with open(local_state_path, 'r') as f:
        local_state = json.load(f)
    
    encrypted_key = local_state['os_crypt']['encrypted_key']
    # The key is base64-encoded, and the first 5 bytes are 'DPAPI'
    encrypted_key = base64.b64decode(encrypted_key)
    assert encrypted_key[:5] == b'DPAPI', f"Expected DPAPI prefix, got {encrypted_key[:5]}"
    encrypted_key = encrypted_key[5:]  # Remove 'DPAPI' prefix
    
    # On Linux, Chrome 80+ uses AES-256-GCM with a fixed key
    # The key is encrypted and stored, but on many Linux systems
    # it's actually stored as plaintext after the DPAPI prefix removal
    # Let's try - on some Linux configs the key is actually plaintext
    if len(encrypted_key) == 256:
        # It's likely a proper encrypted key - need to use the secret service
        # Fall back to the older method
        pass
    
    return encrypted_key

def get_cookies_v10():
    """Chrome v1.0 encryption - plaintext."""
    try:
        db_path = os.path.join(CHROME_PATH, "Default", "Cookies")
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT host_key, name, value FROM cookies WHERE host_key LIKE '%x.com' OR host_key LIKE '%twitter.com'")
        rows = cursor.fetchall()
        conn.close()
        
        cookies = {}
        for host, name, value in rows:
            if name in ('auth_token', 'ct0', 'twid', 'guest_id'):
                cookies[name] = value
                print(f"  {name} (from {host})")
        
        return cookies
    except Exception as e:
        print(f"v10 failed: {e}")
        return {}

def decrypt_value_v11(encrypted_value, key):
    """Decrypt Chrome v1.1+ encrypted cookie value."""
    if not encrypted_value:
        return None
    
    try:
        # Chrome 80+ format: 'v10' or 'v11' prefix + nonce(12 bytes) + ciphertext + tag(16 bytes)
        if encrypted_value.startswith(b'v10') or encrypted_value.startswith(b'v11'):
            nonce = encrypted_value[3:15]
            ciphertext = encrypted_value[15:-16]
            tag = encrypted_value[-16:]
            
            # AES-256-GCM
            aesgcm = AESGCM(key)
            decrypted = aesgcm.decrypt(nonce, ciphertext + tag, None)
            return decrypted.decode('utf-8')
        else:
            return encrypted_value.decode('utf-8', errors='replace')
    except Exception as e:
        print(f"    Decryption failed: {e}")
        return None

def get_linux_key_from_local_state():
    """Get the raw decryption key from Local State."""
    local_state_path = os.path.join(CHROME_PATH, "Local State")
    with open(local_state_path, 'r') as f:
        local_state = json.load(f)
    
    encrypted_key_b64 = local_state['os_crypt']['encrypted_key']
    encrypted_key = base64.b64decode(encrypted_key_b64)
    
    # Remove 'DPAPI' prefix
    if encrypted_key[:5] == b'DPAPI':
        encrypted_key = encrypted_key[5:]
    
    # On some Linux setups, the key might be the raw key we need
    return encrypted_key

def try_get_chrome_key_from_query():
    """Try to query the Chromium keyring secret."""
    import subprocess
    try:
        result = subprocess.run(
            ['secret-tool', 'search', '--unlock', 'application', 'chrome'],
            capture_output=True, text=True, timeout=5
        )
        print(f"  secret-tool stdout: {result.stdout[:200]}")
        print(f"  secret-tool stderr: {result.stderr[:200]}")
    except Exception as e:
        print(f"  secret-tool failed: {e}")

def get_cookies_v11():
    """Chrome v1.1+ encryption - AES-256-GCM."""
    db_path = os.path.join(CHROME_PATH, "Default", "Cookies")
    
    # Get encryption key
    local_state_path = os.path.join(CHROME_PATH, "Local State")
    with open(local_state_path, 'r') as f:
        local_state = json.load(f)
    
    encrypted_key_b64 = local_state['os_crypt']['encrypted_key']
    encrypted_key = base64.b64decode(encrypted_key_b64)
    
    if encrypted_key[:5] == b'DPAPI':
        encrypted_key = encrypted_key[5:]
    
    print(f"  Encrypted key length: {len(encrypted_key)}")
    print(f"  Encrypted key hex (first 20): {encrypted_key[:20].hex()}")
    
    # On Linux with no keyring, Chrome might store the key in plaintext
    # after the DPAPI prefix. Let's try treating it as the raw AES key.
    
    # The key should be 256 bits = 32 bytes for AES-256
    # If it's longer, it might still have encryption wrapper
    
    # For modern Chrome on Linux, the key is stored in the user's keyring
    # We need to use libsecret to retrieve it
    
    try:
        import gi
        gi.require_version('Secret', '1')
        from gi.repository import Secret
        
        schema = Secret.Schema(
            "chrome_libsecret_os_crypt_password_v2",
            Secret.SchemaFlags.NONE,
            [("application", Secret.SchemaAttributeType.STRING)]
        )
        
        attributes = {"application": "chrome"}
        passwords = Secret.password_search_sync(schema, attributes, Secret.SearchFlags.UNLOCK)
        
        print(f"  Found {len(passwords)} keyring entries")
        for p in passwords:
            print(f"    Keyring entry: {p}")
            if isinstance(p, dict) and 'value' in p:
                print(f"    Value: {p['value']}")
                key = base64.b64decode(p['value'])
                if len(key) == 32:
                    print(f"    Got 32-byte AES key!")
                    return key
    except Exception as e:
        print(f"  libsecret approach failed: {e}")
    
    # Fallback: try the encrypted key directly
    # Some Linux configurations store the key in plaintext after DPAPI
    if len(encrypted_key) == 32:
        print(f"  Using encrypted_key directly as AES key (32 bytes)")
        return encrypted_key
    
    print(f"  Key is {len(encrypted_key)} bytes, not 32 - trying different approach")
    return encrypted_key

def read_cookies_directly():
    """Try to read cookies from the SQLite database - first approach."""
    db_path = os.path.join(CHROME_PATH, "Default", "Cookies")
    key = get_cookies_v11()
    
    if key is None or len(key) != 32:
        print(f"  Warning: key length is {len(key) if key else 0}, decryption may fail")
    
    conn = sqlite3.connect(db_path)
    conn.text_factory = bytes
    cursor = conn.cursor()
    
    # Get all cookies for x.com and twitter.com
    cursor.execute("""
        SELECT host_key, name, encrypted_value, path, is_secure, is_httponly
        FROM cookies 
        WHERE host_key LIKE '%x.com' OR host_key LIKE '%twitter.com'
    """)
    
    results = {}
    for host, name, enc_val, path, secure, httponly in cursor.fetchall():
        name_str = name.decode('utf-8', errors='replace')
        host_str = host.decode('utf-8', errors='replace')
        
        if name_str in ('auth_token', 'ct0', 'twid', 'guest_id', 'kdt', 'dnt'):
            # Try to decrypt
            value = decrypt_value_v11(enc_val, key)
            if value:
                results[name_str] = value
                print(f"  {name_str} = {value[:20]}... (from {host_str})")
            else:
                print(f"  {name_str} = DECRYPTION FAILED (from {host_str})")
    
    conn.close()
    return results

if __name__ == '__main__':
    print("Extracting Chrome cookies for x.com...")
    
    # First try direct read
    cookies = read_cookies_directly()
    
    if 'auth_token' not in cookies:
        print("\nauth_token not found via direct decryption.")
        print("Trying alternative method...")
        try_get_chrome_key_from_query()
    
    print(f"\nResult: {json.dumps(cookies, indent=2)}")
