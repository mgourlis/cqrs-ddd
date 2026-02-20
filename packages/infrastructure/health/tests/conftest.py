from __future__ import annotations

import sys
from pathlib import Path

_health_src = Path(__file__).resolve().parents[1] / "src"
if _health_src.is_dir() and str(_health_src) not in sys.path:
    sys.path.insert(0, str(_health_src))
