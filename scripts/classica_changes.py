"""Compatibility imports for the shared Classica change parser."""
from pathlib import Path
import sys

source_root = Path(__file__).resolve().parents[1] / "src"
if str(source_root) not in sys.path:
    sys.path.insert(0, str(source_root))

from cosmo_tiling.parsers.classica_changes import *  # noqa: F401,F403,E402
