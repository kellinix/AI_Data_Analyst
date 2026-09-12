"""
Whole-word keyword matching for column names.

Column-name vocabularies were matched as raw substrings, which quietly
misclassified real data: "arr" matched inside "n**arr**ative", so narrative text
columns in a government project dataset were typed as annual recurring revenue
and summed as money. Matching whole tokens fixes that, and singularising them
keeps plurals working, so "whole life costs" still matches the keyword "cost".
"""

from __future__ import annotations

import re
from collections.abc import Iterable


def normalize_tokens(value: str) -> str:
    """Lowercase, split on non-alphanumerics, drop a trailing "s" from each
    token, and pad with spaces so callers can test whole-token containment."""
    tokens = [token.rstrip("s") or token for token in re.split(r"[^a-z0-9]+", value.lower()) if token]
    return f" {' '.join(tokens)} "


_WITHHELD_VALUE_RE = re.compile(
    r"\b(exempt|redacted|withheld|confidential|commercially\s+sensitive|"
    r"not\s+(available|applicable|disclosed|reported|published)|tbc|tbd)\b",
    re.IGNORECASE,
)

# Deliberately separate from the withheld vocabulary above: a blank-ish label is
# fine to fold into one slice of a chart, but it is not evidence that a numeric
# column was redacted, and widening the withheld rule would change cleaning.
_BLANK_CATEGORY_RE = re.compile(r"^(unknown|unspecified|undisclosed|none|null|n/?a|-|\.)$", re.IGNORECASE)


def is_withheld_value(text: str) -> bool:
    """Whether a cell says its value was withheld rather than being absent.

    Government publications routinely carry "Exempt under Section 43 of the
    Freedom of Information Act 2000" inside otherwise numeric columns, so this
    decides whether such a cell is evidence that a column is text.
    """
    return bool(_WITHHELD_VALUE_RE.search(text))


def is_unreported_category(text: str) -> bool:
    """Whether a category value carries no information about the record.

    The GMPP delivery-confidence column holds five real RAG states plus six
    different FOI-exemption sentences and an "Unknown"; charting all eleven
    stacks six invisible segments labelled with a paragraph each.
    """
    stripped = text.strip()
    return bool(_BLANK_CATEGORY_RE.match(stripped)) or is_withheld_value(stripped)


def shorten_label(text: str, limit: int = 48) -> str:
    """Trim a column label to something that fits on one line.

    Government and survey exports name a column with its whole definition: the
    GMPP delivery-confidence column runs to 200 characters, which is unreadable
    in a chart title and worse inside a sentence. Cuts on a word boundary and
    marks the cut, so a reader can tell the name was shortened.
    """
    cleaned = " ".join(str(text).split())
    if len(cleaned) <= limit:
        return cleaned
    kept: list[str] = []
    length = 0
    for word in cleaned.split(" "):
        extra = len(word) + (1 if kept else 0)
        if length + extra > limit:
            break
        kept.append(word)
        length += extra
    return f"{' '.join(kept)}…" if kept else f"{cleaned[:limit]}…"


def contains_keyword(value: str, keywords: Iterable[str]) -> bool:
    """True when any keyword appears in `value` as whole token(s).

    Keywords may be phrases ("net_revenue", "average order value"); they match
    only as consecutive tokens.
    """
    haystack = normalize_tokens(value)
    return any(normalize_tokens(keyword) in haystack for keyword in keywords if keyword.strip())
