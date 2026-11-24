"""Legacy EP24 merge lab: automatic label deduplication and the researcher review it feeds (#300).

The package is deliberately outside ``src/laclaugpt_visualization``: it is a curation tool for the
legacy EP24 corpus, not part of the AI26 visualization package, and it never imports one.
"""
from __future__ import annotations

__all__ = ["curation", "model", "normalization", "similarity", "sources"]
