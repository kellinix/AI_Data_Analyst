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


def contains_keyword(value: str, keywords: Iterable[str]) -> bool:
    """True when any keyword appears in `value` as whole token(s).

    Keywords may be phrases ("net_revenue", "average order value"); they match
    only as consecutive tokens.
    """
    haystack = normalize_tokens(value)
    return any(normalize_tokens(keyword) in haystack for keyword in keywords if keyword.strip())
