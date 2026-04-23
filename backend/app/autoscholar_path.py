from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = PROJECT_ROOT / "backend"
AUTOSCHOLAR_ROOT = PROJECT_ROOT / "AutoScholar"
AUTOSCHOLAR_SRC = AUTOSCHOLAR_ROOT / "src"

if str(AUTOSCHOLAR_SRC) not in sys.path:
    sys.path.insert(0, str(AUTOSCHOLAR_SRC))
