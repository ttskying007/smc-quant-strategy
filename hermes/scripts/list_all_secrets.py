#!/usr/bin/env python3
"""List all secrets in the keyring to find Chrome's encryption key."""
import gi
gi.require_version('Secret', '1')
from gi.repository import Secret, GLib

# Connect to the secret service
service = Secret.Service.get_sync(Secret.ServiceFlags.OPEN_SESSION)
print("Connected to secret service")

# Get default collection
collections = service.get_collections()
print(f"Collections: {len(collections)}")
for col in collections:
    print(f"  Collection: {col.get_label()} (locked: {col.get_is_locked()})")
    
    if col.get_is_locked():
        print("    -> Unlocking...")
        col.unlock_sync()
    
    items = col.get_items()
    print(f"    Items: {len(items)}")
    for item in items:
        label = item.get_label()
        attrs = item.get_attributes()
        print(f"      '{label}'")
        for k, v in attrs.items():
            print(f"        {k} = {v}")
        
        # Try to get the secret
        if hasattr(item, 'get_secret_sync'):
            secret = item.get_secret_sync()
            if secret:
                text = secret.get_text()
                val = text.strip() if text else "(empty)"
                print(f"        value (first 50): {val[:50]}")
                print(f"        value hex (first 20): {val[:20].encode().hex()}")
