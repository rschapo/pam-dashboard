import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]           # generator/complementary
for sub in (ROOT, ROOT / "process", ROOT / "quality", ROOT / "download"):
    sys.path.insert(0, str(sub))
