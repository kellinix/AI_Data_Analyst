"""
Shared SQL helpers for the DuckDB-backed analytics modules.

`quote_identifier` was previously defined independently in five places
(`statistics.py`, `data_quality.py`, `anomaly_detection.py`, `forecasting.py`,
`live_filter.py`) — byte-identical in every copy. Consolidated here as a pure
refactor: every call site behaves exactly as before, since the
implementation is unchanged.
"""

from __future__ import annotations


def quote_identifier(identifier: str) -> str:
    """Double-quote a DuckDB column/table identifier, escaping embedded
    quotes, so a column name can be safely interpolated into a SQL string
    without a caller having to remember to do it themselves."""
    return '"' + identifier.replace('"', '""') + '"'
