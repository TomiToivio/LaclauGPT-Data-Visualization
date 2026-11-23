"""Search across the PLEDGE grievance frame, as one testable rule.

Why this module exists: the dashboard's search inspected ``grievances`` only, so a universal
number (``video_id``, e.g. ``HEPP24-ES-CR-IG-20240520-1081000``) could never match — the field
was not searched at all. It also used ``str.contains`` with its default ``regex=True``, so a query
containing ``(``, ``+`` or ``.`` was read as a pattern and either missed or raised.

Two fixes, one rule: search a *chosen* set of columns, and match the query literally.
"""

from __future__ import annotations

import pandas as pd

#: Label shown in the sidebar -> the columns it searches.
SEARCH_SCOPES: dict[str, tuple[str, ...]] = {
    "All fields": ("video_id", "grievances", "topics", "entities", "themes", "persons"),
    "Universal number": ("video_id",),
    "Grievances": ("grievances",),
    "Topics": ("topics",),
    "Entities": ("entities",),
    "Themes": ("themes",),
    "Persons": ("persons",),
}


def search_frame(frame: pd.DataFrame, query: str, scope: str = "All fields") -> pd.DataFrame:
    """Rows where any searched column contains ``query`` as a literal, case-insensitively."""
    query = (query or "").strip()
    if not query or frame.empty:
        return frame
    columns = [column for column in SEARCH_SCOPES.get(scope, SEARCH_SCOPES["All fields"]) if column in frame.columns]
    if not columns:
        return frame.iloc[0:0]
    haystack = frame[columns].astype(str).agg(" ".join, axis=1)
    # regex=False: a universal number or a grievance may contain characters that are pattern
    # syntax, and the researcher is typing text, not an expression.
    return frame[haystack.str.contains(query, case=False, na=False, regex=False)]
