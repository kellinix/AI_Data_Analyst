"""
Plain English for the text the model writes.

Prompt instructions were not enough. Told explicitly never to write "outlier",
"anomaly" or "dataset", a *successful* response still produced: "significant
financial variances and outliers in the dataset ... These anomalies suggest
areas for further investigation." The model echoes the vocabulary of the
profile it is handed, so the wording is corrected here rather than requested.

Deliberately not replaced: "variance", "baseline", "forecast" and similar —
they are the reader's own column names, not statistics jargon, and swapping
them would make the text wrong rather than plain.
"""

from __future__ import annotations

import re
from typing import Any

_REPLACEMENTS: tuple[tuple[str, str], ...] = (
    # A like-for-like noun, so it reads correctly wherever the original sat.
    # The first choice, "unusually high or low figures", broke after
    # adjectives: the model's "shows notable financial outliers" rendered as
    # "shows notable financial unusually high or low figures".
    (r"\boutliers\b", "extremes"),
    (r"\boutlier\b", "extreme figure"),
    (r"\banomalies\b", "unusual results"),
    (r"\banomaly\b", "unusual result"),
    (r"\bdatasets\b", "files"),
    (r"\bdataset\b", "file"),
    (r"\bcorrelations\b", "relationships"),
    (r"\bcorrelation\b", "relationship"),
    (r"\bdistributions\b", "spreads"),
    (r"\bdistribution\b", "spread"),
    (r"\bhistograms\b", "bar charts"),
    (r"\bhistogram\b", "bar chart"),
    (r"\bpercentiles\b", "rankings"),
    (r"\bpercentile\b", "ranking"),
    (r"\blogarithmic\b", "wide-ranging"),
    (r"\bz-?scores\b", "distances from the average"),
    (r"\bz-?score\b", "distance from the average"),
    (r"\bstandard deviations\b", "typical variations"),
    (r"\bstandard deviation\b", "typical variation"),
    (r"\brecords\b", "entries"),
    (r"\brecord\b", "entry"),
    (r"\brows\b", "entries"),
    (r"\bcolumns\b", "fields"),
)

_TEXT_FIELDS = (
    "executive_summary", "title", "description", "problem", "evidence",
    "expected_impact", "recommendation",
)


def plain_english(text: str) -> str:
    """Swap statistics vocabulary for words a business reader already has."""
    result = str(text)
    for pattern, replacement in _REPLACEMENTS:
        # IGNORECASE matters more than it looks: without it a sentence opening
        # with "Outliers ..." or "Anomalies ..." passed straight through, which
        # is exactly how a model starts a sentence. The lambda below then puts
        # the capital back.
        result = re.sub(
            pattern,
            lambda match, word=replacement: (
                word[:1].upper() + word[1:] if match.group(0)[:1].isupper() else word
            ),
            result,
            flags=re.IGNORECASE,
        )
    return result


def plain_english_in_place(value: Any) -> Any:
    """Apply `plain_english` to every reader-facing string in an AI result.

    Walks the structure rather than naming paths, so a new field in the
    model's output cannot quietly reintroduce the vocabulary.
    """
    if isinstance(value, dict):
        return {
            key: (
                plain_english(item)
                if isinstance(item, str) and key in _TEXT_FIELDS
                else plain_english_in_place(item)
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [plain_english_in_place(item) for item in value]
    return value
