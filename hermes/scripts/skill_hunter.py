#!/usr/bin/env python3
"""
Cron: Daily SMC/Hermes Skill Hunter
Scrapes X/Reddit/GitHub/Google for trending SMC trading skills,
Hermes Agent tools, prompts, and related resources.
"""
import json, os, shutil, subprocess, time
from datetime import datetime

XCRAWL_KEY = "xc-purV9otHhd1XjUHObnT4HUsfPMhVWa7rGNYW7xBLH8IsToMm"
OUTPUT_DIR = "/home/lei/.skill_hunter"
os.makedirs(OUTPUT_DIR, exist_ok=True)

def xcrawl_search(query, limit=5, tbs="qdr:w", timeout=25):
    """Search via curl subprocess — urllib.request is broken for XCrawl
    (SSL EOF without proxy, HTTP 403 with ProxyHandler)."""
    curl = shutil.which("curl")
    if not curl:
        return {"error": "curl not found"}
    data = json.dumps({"query": query, "limit": limit, "tbs": tbs})
    try:
        p = subprocess.run(
            [curl, "-s", "--connect-timeout", "10", "--max-time", str(timeout),
             "--noproxy", "*",
             "-X", "POST", "https://run.xcrawl.com/v1/search",
             "-H", "Content-Type: application/json",
             "-H", f"Authorization: Bearer {XCRAWL_KEY}",
             "-d", data],
            capture_output=True, text=True, timeout=timeout+5
        )
        if p.returncode != 0:
            return {"error": f"curl exit {p.returncode}: {p.stderr[:200]}"}
        return json.loads(p.stdout)
    except json.JSONDecodeError as e:
        return {"error": f"json decode: {e}"}
    except subprocess.TimeoutExpired:
        return {"error": "timeout"}
    except Exception as e:
        return {"error": str(e)}

def main():
    print(f"[{datetime.now().isoformat()}] SMC/Hermes Skill Hunter starting...")
    
    # Search queries for SMC trading
    smc_queries = [
        "SMC trading ICT strategy 2026",
        "Smart Money Concepts trading bot github",
        "FVG order block detector python",
        "ICT forex strategy backtest",
        "SMC交易系统 策略",
        "supply demand trading indicator"
    ]
    
    # Search queries for Hermes Agent
    hermes_queries = [
        "Hermes Agent NousResearch skills tools",
        "agent framework skills prompt engineering 2026",
        "AI trading agent tool calling",
        "hermes agent custom skill development",
        "LLM agent trading bot architecture",
        "自动交易系统 AI agent"
    ]
    
    all_results = {"smc": [], "hermes": [], "timestamp": datetime.now().isoformat()}
    
    for q in smc_queries + hermes_queries:
        print(f"  Searching: {q[:50]}...")
        result = xcrawl_search(q, limit=5)
        if "error" in result:
            print(f"    Error: {result['error']}")
            continue
        items = result.get("data", {}).get("data", [])
        for item in items:
            url = item.get("url", "")
            entry = {
                "title": item.get("title", ""),
                "link": url,
                "description": item.get("description", "")[:200],
                "source": "github" if "github.com" in url else "reddit" if "reddit.com" in url else "other"
            }
            # Tag by category
            is_smc = any(k in (entry["title"]+entry["description"]).lower() 
                        for k in ["smc", "fvg", "order block", "ict", "smart money", "liquidity", "forex", "trading strategy", "backtest"])
            if is_smc:
                all_results["smc"].append(entry)
            else:
                all_results["hermes"].append(entry)
    
    # Save results
    today = datetime.now().strftime("%Y%m%d")
    path = f"{OUTPUT_DIR}/hunt_{today}.json"
    with open(path, 'w') as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)
    
    print(f"\n  Results saved: {path}")
    print(f"  SMC items: {len(all_results['smc'])}")
    print(f"  Hermes items: {len(all_results['hermes'])}")
    
    # Print top finds
    for cat in ["smc", "hermes"]:
        if all_results[cat]:
            print(f"\n  Top {cat.upper()} finds:")
            for item in all_results[cat][:5]:
                print(f"    - {item['title'][:80]}")
                print(f"      {item['link'][:80]}")
    
    print(f"[{datetime.now().isoformat()}] Done.")

if __name__ == "__main__":
    main()