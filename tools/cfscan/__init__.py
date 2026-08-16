"""Static scans over the Crossfire map set.

Reproduces the figures quoted in difficulty-notes.txt, and emits the per-map
rows behind them so each one is a work queue rather than a percentage.
"""

from .archetypes import Archetypes, load_exp_table
from .mapset import MapSet, MapFile, MapObject
from .reports import REPORTS, Report

__all__ = [
    "Archetypes",
    "load_exp_table",
    "MapSet",
    "MapFile",
    "MapObject",
    "REPORTS",
    "Report",
]
