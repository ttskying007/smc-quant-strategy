#!/usr/bin/env python3
"""
Cron: Daily Clash Subscription Hunter
Searches X/Reddit/Google/GitHub for free Clash Meta subscriptions,
tests them, and updates the active config. Keeps 30-day history.
"""
import json, os, time, subprocess, sys
import urllib.request
from datetime import datetime, timedelta

# Config
XCRAWL_KEY = "xc-purV9otHhd1XjUHObnT4HUsfPMhVWa7rGNYW7xBLH8IsToMm"
XCRAWL_URL = "https://run.xcrawl.com/v1/search"
HISTORY_DIR = "/home/lei/.clash_history"
ACTIVE_CONFIG = "/home/lei/.clash_merged.yaml"
CLASH_DIR = "/root/.clash"
os.makedirs(HISTORY_DIR, exist_ok=True)

def xcrawl_search(query, limit=5, tbs="qdr:w"):
    """Search via xcrawl API."""
    import urllib.request
    data = json.dumps({"query": query, "limit": limit, "tbs": tbs}).encode()
    req = urllib.request.Request(XCRAWL_URL, data=data, headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {XCRAWL_KEY}"
    })
    try:
        resp = urllib.request.urlopen(req, timeout=30)
        return json.loads(resp.read())
    except Exception as e:
        return {"error": str(e)}

def fetch_url(url, timeout=15):
    """Download a URL with timeout."""
    import urllib.request
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
        return resp.read()
    except:
        return None

def test_proxy_yaml(data):
    """Quick check if content looks like a valid Clash config with proxies."""
    if not data:
        return False
    text = data.decode('utf-8', errors='replace')
    return 'proxies:' in text and '- name:' in text and ('mixed-port:' in text or 'port:' in text)

def main():
    print(f"[{datetime.now().isoformat()}] Clash Subscription Hunter starting...")
    
    # Step 1: Search multiple sources
    queries = [
        "clash meta subscription free site:github.com",
        "clash node free 2026 site:reddit.com",
        "free clash subscription 2026",
        "clash meta yaml subscription free",
        "mihomo config free node 2026",
        "clash订阅 免费 2026"  # Chinese
    ]
    
    found_urls = []
    for q in queries:
        print(f"  Searching: {q[:50]}...")
        result = xcrawl_search(q, limit=3)
        if "error" in result:
            print(f"    Error: {result['error']}")
            continue
        data = result.get("data", {}).get("data", [])
        for item in data:
            link = item.get("link", "")
            if link and "yaml" in link.lower() or "sub" in link.lower() or "clash" in link.lower():
                found_urls.append(link)
    
    # Step 2: Try known free subscription sources
    known_sources = [
        f"https://node.freeclashnode.com/uploads/{datetime.now().strftime('%Y/%m')}/0-{datetime.now().strftime('%Y%m%d')}.yaml",
        f"https://node.freeclashnode.com/uploads/{datetime.now().strftime('%Y/%m')}/1-{datetime.now().strftime('%Y%m%d')}.yaml",
    ]
    found_urls.extend(known_sources)
    
    # Step 3: Download and test each
    print(f"\n  Found {len(found_urls)} potential URLs. Testing...")
    best_data = None
    best_url = None
    
    for url in set(found_urls):
        print(f"    Testing: {url[:80]}...")
        data = fetch_url(url, timeout=20)
        if data and test_proxy_yaml(data):
            # Check size - at least 10KB suggests real proxies
            if len(data) > 10000:
                best_data = data
                best_url = url
                print(f"    ✓ VALID ({len(data)} bytes)")
            else:
                print(f"    Too small ({len(data)} bytes)")
        else:
            print(f"    ✗ Invalid or timeout")
    
    # Step 4: If found something better, update
    if best_data:
        # Save history
        today = datetime.now().strftime("%Y%m%d")
        history_path = f"{HISTORY_DIR}/clash_{today}.yaml"
        with open(history_path, 'wb') as f:
            f.write(best_data)
        print(f"\n  Saved history: {history_path}")
        
        # Update active config
        with open(ACTIVE_CONFIG, 'wb') as f:
            f.write(best_data)
        print(f"  Updated active config: {ACTIVE_CONFIG}")
        
        # Restart mihomo
        subprocess.run(["pkill", "-9", "mihomo"], capture_output=True)
        time.sleep(2)
        subprocess.Popen(["mihomo", "-d", CLASH_DIR, "-f", ACTIVE_CONFIG],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print(f"  mihomo restarted with new config from: {best_url[:80]}")

        # Post-restart: ensure GLOBAL is set to auto-select (not DIRECT)
        # Otherwise unmatched domains (like integrate.api.nvidia.com) timeout
        time.sleep(3)
        for attempt in range(5):
            try:
                req = urllib.request.Request(
                    "http://127.0.0.1:9090/proxies/GLOBAL",
                    data=json.dumps({"name": "♻️ 自动选择"}).encode(),
                    method="PUT"
                )
                urllib.request.urlopen(req, timeout=5)
                print(f"  GLOBAL set to ♻️ 自动选择")
                # V21: Also set 🚀 节点选择 to 美國節點_2 (bypass broken URLTest)
                # URLTest auto-selects by HTTP latency but picks TLS-dead nodes
                # (德國_1, 英國 — gstatic passes, real HTTPS fails)
                time.sleep(2)
                try:
                    route_req = urllib.request.Request(
                        "http://127.0.0.1:9090/proxies/%F0%9F%9A%80%20%E8%8A%82%E7%82%B9%E9%80%89%E6%8B%A9",
                        data=json.dumps({"name": "美國節點_2"}).encode(),
                        method="PUT"
                    )
                    urllib.request.urlopen(route_req, timeout=5)
                    print(f"  🚀 节点选择 set to 美國節點_2 (bypass URLTest)")
                except Exception as e:
                    print(f"  ⚠ Failed to set 节点选择: {e}")
                # V20.1: Verify TLS connectivity
                time.sleep(5)  # Let changes settle
                tls_ok = False
                for tls_test_url in [
                    "https://api.deepseek.com/v1/models",
                    "https://integrate.api.nvidia.com/v1/models",
                ]:
                    try:
                        tls_req = urllib.request.Request(tls_test_url)
                        tls_req.set_proxy("http://127.0.0.1:7890", "https")
                        resp = urllib.request.urlopen(tls_req, timeout=10)
                        code = resp.getcode()
                        if code in (200, 401, 404):
                            tls_ok = True
                            print(f"  ✅ TLS test OK ({tls_test_url.split('/')[2]} → {code})")
                            break
                    except Exception:
                        continue
                if not tls_ok:
                    # Try fallback: set 🚀 节点选择 directly (bypass broken URLTest)
                    fallback_nodes = ["美國節點_2", "美國_3", "德國", "英國_6"]
                    for fb_node in fallback_nodes:
                        try:
                            fb_req = urllib.request.Request(
                                "http://127.0.0.1:9090/proxies/%F0%9F%9A%80%20%E8%8A%82%E7%82%B9%E9%80%89%E6%8B%A9",
                                data=json.dumps({"name": fb_node}).encode(),
                                method="PUT"
                            )
                            urllib.request.urlopen(fb_req, timeout=5)
                            time.sleep(3)
                            # Verify TLS
                            tls_req2 = urllib.request.Request("https://integrate.api.nvidia.com/v1/models")
                            tls_req2.set_proxy("http://127.0.0.1:7890", "https")
                            resp2 = urllib.request.urlopen(tls_req2, timeout=10)
                            if resp2.getcode() in (200, 401):
                                print(f"  🚀 节点选择 → {fb_node} (TLS-verified fallback)")
                                break
                        except Exception:
                            continue
                    else:
                        print(f"  ⚠ All fallback nodes TLS-dead! Keeping current routing.")
                break
            except Exception as e:
                if attempt < 4:
                    time.sleep(2)
                else:
                    print(f"  ⚠ Failed to set GLOBAL after 5 attempts: {e}")
    else:
        print("\n  No better config found today. Current config kept.")
    
    # Step 5: Cleanup old history (>30 days)
    cutoff = datetime.now() - timedelta(days=30)
    for f in os.listdir(HISTORY_DIR):
        fpath = os.path.join(HISTORY_DIR, f)
        if os.path.isfile(fpath):
            mtime = datetime.fromtimestamp(os.path.getmtime(fpath))
            if mtime < cutoff:
                os.remove(fpath)
                print(f"  Purged old: {f}")
    
    print(f"[{datetime.now().isoformat()}] Done.")

if __name__ == "__main__":
    main()