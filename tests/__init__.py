import sys
from pathlib import Path

# Source modules use flat imports (e.g. `import sll_algorithm3`), so expose their folders.
ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "generator"), str(ROOT / "sat_attack")]
