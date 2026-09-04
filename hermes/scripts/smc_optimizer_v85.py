#!/usr/bin/env python3
"""
SMC V8.5 Auto Optimizer — Multi-round adaptive optimization
===========================================================
Goal: WR > 85% with consistent RR > 2.0

Architecture:
  - Runs V8.4 engine cycles (300 iters each)
  - Progressive tightening: 0.20 → 0.25 → 0.30 → 0.35 → 0.40 → 0.45
  - Adaptive target: WR >= 85% → success; auto-increment if exceeded
  - Early stop: no WR improvement for 3 consecutive rounds
  - Auto-resume from best seed
  - Proxy status check before each round (waits for proxy if down)
  - Logs all rounds to optimizer_log.json

Run:
  python3 smc_optimizer_v85.py              # default: 6 rounds max
  python3 smc_optimizer_v85.py --rounds 10  # custom max rounds
  python3 smc_optimizer_v85.py --target 90  # custom WR target
"""
import sys, os, json, time, subprocess, signal
from pathlib import Path
from datetime import datetime

HOME = Path.home()
SCRIPTS_DIR = HOME / '.hermes' / 'scripts'
LOG_DIR = HOME / '.hermes' / 'smc_opt_v83'
LOGS_DIR = HOME / '.hermes' / 'logs'

for d in [LOG_DIR, LOGS_DIR]:
    d.mkdir(parents=True, exist_ok=True)

OPTIMIZER = SCRIPTS_DIR / 'smc_optimizer_v84.py'

# ════════════════════════════════════════════
# Config
# ════════════════════════════════════════════

MAX_ROUNDS = 6
TARGET_WR = 85.0
ROUND_ITERS = 300
ROUND_STOCKS = 40
TIGHTEN_SEQUENCE = [0.0, 0.25, 0.30, 0.35, 0.40, 0.45]
EARLY_STOP_ROUNDS = 3  # consecutive rounds without improvement

current_process = None

# ════════════════════════════════════════════
# Helpers
# ════════════════════════════════════════════

def log(msg):
    timestamp = datetime.now().strftime('%H:%M:%S')
    line = f"[{timestamp}] {msg}"
    print(line)
    with open(LOGS_DIR / 'smc_optimizer_v85.log', 'a') as f:
        f.write(line + '\n')

def safe_read_json(path):
    try:
        if path and Path(path).exists():
            return json.loads(Path(path).read_text())
    except: pass
    return {}

def get_best_wr():
    status = safe_read_json(LOG_DIR / 'live_status.json')
    return float(status.get('best_wr', 0))

def save_best_as_seed(round_num):
    """Save current best params as seed for next round"""
    best = safe_read_json(LOG_DIR / 'best_params.json')
    if best:
        seed_path = LOG_DIR / f'seed_round_{round_num}.json'
        seed_path.write_text(json.dumps(best, ensure_ascii=False, indent=2))
        return str(seed_path)
    return None

def check_proxy():
    """Wait for proxy to be ready"""
    max_wait = 120
    waited = 0
    while waited < max_wait:
        try:
            import urllib.request
            req = urllib.request.Request('http://127.0.0.1:9090/proxies')
            with urllib.request.urlopen(req, timeout=2) as r:
                data = json.loads(r.read().decode())
                if data.get('proxies'):
                    return True
        except:
            pass
        # Check port
        import socket
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.settimeout(1)
            s.connect(('127.0.0.1', 7890))
            s.close()
            return True
        except:
            pass
        time.sleep(3)
        waited += 3
        print(f"  ⏳ Waiting for proxy... ({waited}s)")
    return False

def wait_for_round_complete(check_interval=10, max_wait=600):
    """Poll live_status.json until round completes"""
    waited = 0
    last_round = 0
    start_wr = get_best_wr()
    while waited < max_wait:
        status = safe_read_json(LOG_DIR / 'live_status.json')
        current_round = status.get('round', 0)
        status_val = status.get('status', '')
        if status_val == 'complete':
            return True
        if current_round > last_round and waited % 20 == 0:
            wr_now = get_best_wr()
            log(f"    Round {current_round}/{ROUND_ITERS} — Best WR: {wr_now}%")
            last_round = current_round
        time.sleep(check_interval)
        waited += check_interval
    return False

def run_optimizer_round(iters, stocks, tighten, seed):
    """Run a single optimizer round"""
    global current_process
    cmd = [
        sys.executable, str(OPTIMIZER),
        str(iters), str(stocks),
    ]
    if tighten > 0:
        cmd.extend(['--tighten', str(tighten)])
    if seed:
        cmd.extend(['--seed', str(seed)])
    
    log(f"  Command: {' '.join(cmd)}")
    start = time.time()
    
    # Clear status
    write_status('running', 0, iters)
    
    # Run in background
    log_path = str(LOGS_DIR / 'smc_optimizer.log')
    with open(log_path, 'a') as f:
        f.write(f"\n--- Round {round_num} (tighten={tighten}) {datetime.now().isoformat()} ---\n")
        current_process = subprocess.Popen(cmd, stdout=f, stderr=subprocess.STDOUT)
    
    # Wait
    current_process.wait()
    elapsed = time.time() - start
    current_process = None
    
    # Get results
    status = safe_read_json(LOG_DIR / 'live_status.json')
    best_wr = float(status.get('best_wr', 0))
    best_n = int(status.get('best_n', 0))
    best_rr = float(status.get('best_rr', 0))
    best_pf = float(status.get('best_pf', 0))
    
    write_status('complete', iters, iters, best_wr=best_wr)
    
    log(f"  ⏱ {elapsed:.0f}s — WR={best_wr}% N={best_n} RR={best_rr} PF={best_pf}")
    return best_wr, best_n, best_rr, best_pf

def write_status(st, rnd, total, best_wr=0):
    """Update live_status.json"""
    state = safe_read_json(LOG_DIR / 'live_status.json')
    state['status'] = st
    state['round'] = rnd
    state['total_rounds'] = total
    state['timestamp'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    if best_wr:
        state['best_wr'] = best_wr
    (LOG_DIR / 'live_status.json').write_text(json.dumps(state, ensure_ascii=False))

# ════════════════════════════════════════════
# Main Loop
# ════════════════════════════════════════════

def main():
    global round_num
    max_rounds = MAX_ROUNDS
    target_wr = TARGET_WR
    
    # Parse args
    for i, a in enumerate(sys.argv[1:]):
        if a == '--rounds' and i + 1 < len(sys.argv):
            max_rounds = int(sys.argv[i + 2])
        if a == '--target' and i + 1 < len(sys.argv):
            target_wr = float(sys.argv[i + 2])
    
    print(f"""
╔═══════════════════════════════════════════════════════════╗
║  SMC V8.5 Auto Optimizer                                  ║
║  Target WR: ≥{target_wr}% | Max Rounds: {max_rounds}     ║
║  Tighten: {TIGHTEN_SEQUENCE}                              ║
║  Early Stop: {EARLY_STOP_ROUNDS} rounds no improvement    ║
╚═══════════════════════════════════════════════════════════╝
""")
    
    # Check proxy
    log("Checking proxy connectivity...")
    proxy_ok = check_proxy()
    log(f"  Proxy: {'OK' if proxy_ok else 'WARN — continuing anyway'}")
    
    # Initialize log
    round_log = []
    best_overall_wr = 0
    best_overall_seed = None
    no_improvement_count = 0
    
    for round_num in range(1, max_rounds + 1):
        tighten = TIGHTEN_SEQUENCE[min(round_num-1, len(TIGHTEN_SEQUENCE)-1)]
        
        print(f"\n{'='*60}")
        log(f"Round {round_num}/{max_rounds} — Tighten={tighten} Target=WR≥{target_wr}%")
        print(f"{'='*60}")
        
        # Get seed
        seed = save_best_as_seed(round_num - 1)
        if round_num == 1:
            seed = str(LOG_DIR / 'best_params.json')
        
        # Run round
        wr, n, rr, pf = run_optimizer_round(ROUND_ITERS, ROUND_STOCKS, tighten, seed)
        
        # Record
        round_entry = {
            'round': round_num,
            'tighten': tighten,
            'wr': wr,
            'n': n,
            'rr': rr,
            'pf': pf,
            'seed': seed,
            'time': datetime.now().isoformat(),
        }
        round_log.append(round_entry)
        
        # Save round log
        (LOG_DIR / 'optimizer_log_v85.json').write_text(
            json.dumps(round_log, ensure_ascii=False, indent=2))
        
        # Update best
        if wr > best_overall_wr:
            best_overall_wr = wr
            best_overall_seed = seed
            no_improvement_count = 0
        else:
            no_improvement_count += 1
        
        # Check target
        if wr >= target_wr:
            log(f"🎯 TARGET REACHED! WR={wr}% ≥ {target_wr}%")
            print(f"\n{'★'*50}")
            print(f"  TARGET ACHIEVED: WR={wr}% in {round_num} rounds!")
            print(f"  Final: WR={wr}% N={n} RR={rr} PF={pf}")
            print(f"{'★'*50}\n")
            break
        
        # Early stop
        if no_improvement_count >= EARLY_STOP_ROUNDS:
            log(f"⏹ Early stop: {EARLY_STOP_ROUNDS} rounds without improvement")
            break
        
        # Check proxy before next round
        if round_num < max_rounds:
            log("Verifying proxy for next round...")
            check_proxy()
    
    # Final summary
    print(f"\n{'='*50}")
    print(f"  V8.5 Optimization Complete")
    print(f"  Rounds: {len(round_log)}")
    print(f"  Best WR: {best_overall_wr}%")
    print(f"  Log: {LOG_DIR / 'optimizer_log_v85.json'}")
    print(f"{'='*50}\n")

if __name__ == '__main__':
    main()