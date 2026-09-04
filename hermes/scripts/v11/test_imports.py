#!/usr/bin/env python3
"""快速测试v44引擎导入"""
import sys
sys.path.insert(0, '/root/.hermes/scripts')
try:
    print("Testing imports...")
    from v11.signals_v11 import detect_all_signals_v11, calc_adaptive_thresholds, Signal
    print("  v11.signals_v11 OK")
    from v11.resonance_v11 import evaluate_full_resonance_v11, make_entry_decision_v11
    print("  v11.resonance_v11 OK")
    from v11.sequencer_v11 import analyze_sequence_v11
    print("  v11.sequencer_v11 OK")
    print("All imports OK!")
except Exception as e:
    print(f"ERROR: {e}")
    import traceback; traceback.print_exc()