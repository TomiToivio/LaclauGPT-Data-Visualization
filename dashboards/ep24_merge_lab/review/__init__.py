"""Independent multi-agent review of the legacy label merges (#311).

Freeze an inventory, let three independent models judge every decision unit, keep the whole panel
attributable in a shared ledger, adjudicate disagreements, and publish an immutable release.
"""
from __future__ import annotations

__all__ = ["inventory", "ledger", "providers", "reconcile", "release", "runner", "wikipedia"]
