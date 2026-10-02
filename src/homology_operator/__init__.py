"""Exact F2 single-scale reference backend (unreleased)."""

__version__ = "0.0.2.dev0"

from .algebra import Matrix
from .chain import ChainWindow, InvalidInput

__all__ = ["Matrix", "ChainWindow", "InvalidInput", "__version__"]
