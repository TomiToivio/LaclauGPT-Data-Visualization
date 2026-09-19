"""Tidy node/edge tables for R, Python and external network tools."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pandas as pd

from ._common import normalize_projection


def to_tidy_tables(projection: Mapping[str, Any]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return independent node and edge tables while retaining provenance fields."""
    nodes, edges = normalize_projection(projection)
    return pd.DataFrame(nodes), pd.DataFrame(edges)
