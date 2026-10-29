"""Stable asset paths, independent of which panel requests them."""
from pathlib import Path
PACKAGE_ROOT=Path(__file__).resolve().parents[1]
REPOSITORY_ROOT=PACKAGE_ROOT.parents[1]
