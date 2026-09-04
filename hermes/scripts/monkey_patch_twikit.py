#!/usr/bin/env python3
"""
monkey_patch_twikit.py - Patch twikit v2.3.3 x_client_transaction
Fetches key from X homepage (simple), skips broken KEY_BYTE search.
"""
import math, time, random, hashlib, base64, re, asyncio

def apply_patch():
    try:
        from twikit.x_client_transaction import transaction as tx
        from twikit.x_client_transaction import utils
    except ImportError:
        return False

    # Minimal init - just set defaults
    def patched___init__(self):
        self.home_page_response = None
        self.key = "placeholder"
        self.key_bytes = [0] * 64
        self.animation_key = "0" * 25
        self.DEFAULT_ROW_INDEX = 0
        self.DEFAULT_KEY_BYTES_INDICES = [1, 2, 3]

    # Simplified async init - fetch key from homepage only
    async def patched_init(self, session, headers):
        import bs4
        try:
            resp = await session.request(method="GET", url="https://x.com", headers=headers, follow_redirects=True)
            soup = bs4.BeautifulSoup(resp.content, 'html.parser')
            el = soup.select_one("[name='twitter-site-verification']")
            if el:
                self.key = el.get("content", "")
                self.key_bytes = list(base64.b64decode(bytes(self.key, 'utf-8')))
                self.DEFAULT_ROW_INDEX = self.key_bytes[2] % 16
                print(f"[twikit-patch] Key: {self.key[:20]}...")
        except Exception as e:
            print(f"[twikit-patch] Warning: {e}")

    # Generate transaction ID with fixed animation_key
    def patched_gen_id(self, method, path, response=None, key=None, animation_key=None, time_now=None):
        time_now = time_now or math.floor((time.time() * 1000 - 1682924400 * 1000) / 1000)
        time_now_bytes = [(time_now >> (i * 8)) & 0xFF for i in range(4)]
        k = key or getattr(self, 'key', "placeholder")
        kb = self.key_bytes
        if not kb:
            kb = list(base64.b64decode(bytes(k[:44] + "=", 'utf-8'))) if len(k) >= 44 else [0] * 64
        ak = animation_key or getattr(self, 'animation_key', "0" * 25)
        h = hashlib.sha256(f"{method}!{path}!{time_now}obfiowerehiring{ak}".encode()).digest()
        rn = random.randint(0, 255)
        ba = [*kb, *time_now_bytes, *list(h)[:16], 3]
        out = bytearray([rn, *[item ^ rn for item in ba]])
        return base64.b64encode(out).decode().strip("=")

    tx.ClientTransaction.__init__ = patched___init__
    tx.ClientTransaction.init = patched_init
    tx.ClientTransaction.generate_transaction_id = patched_gen_id
    return True

if __name__ == '__main__':
    apply_patch()
    print("Patch ready. Import this module before using twikit.")
