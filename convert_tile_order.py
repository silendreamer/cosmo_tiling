"""Backward-compatible launcher for the tile-order converter."""

from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parent
SOURCE_ROOT = PROJECT_ROOT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from cosmo_tiling.converter import *  # noqa: E402,F403
from cosmo_tiling.converter import main  # noqa: E402


if __name__ == "__main__":
    main()
