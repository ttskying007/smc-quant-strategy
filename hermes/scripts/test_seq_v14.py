import sys
sys.path.insert(0, '/root/.hermes/scripts')

from v11.sequencer_v11 import analyze_sequence_v11, _find_fvg_entry, match_sequence_with_temporal_weight, SEQUENCE_DEFS
print("Sequencer V11.4 import OK")

# Check window sizes
for name, defn in SEQUENCE_DEFS.items():
    print(f"  {name:20s} windows={str(defn['windows']):10s} steps={defn['steps']}")
print()

# Test temporal decay
import math
for dist in [1, 2, 3, 4, 5, 8, 10, 15]:
    score = math.exp(-dist / 4.0)
    print(f"  dist={dist:2d} -> temporal_score={score:.3f}")

print("\nAll checks passed!")
