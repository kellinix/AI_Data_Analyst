"""
Readable column labels derived deterministically from raw column names.

Display labels used to come only from an AI call, and a *successful* response
was observed returning a column's entire 200-character definition as its
"label" — which then became a chart title, an axis name and a quality-check
heading. One run produced "Baseline Financial Year Cost (M)" and the next
"Financial Year Baseline Currency M Including Non Government Costs" for the
same column. Readability should not depend on which of those comes back, so
the label is derived here and the AI's version is used only when it is
genuinely shorter.
"""

from __future__ import annotations

import re

# Everything from one of these words onward describes the measure rather than
# naming it: "..._including_non_government_costs".
_QUALIFIER_WORDS = frozenset({
    "including", "includes", "excluding", "excludes", "defined", "definition",
    "definitions", "using", "based", "where", "which", "whether", "if", "per",
    "versus", "vs", "than",
})

_ACRONYMS = {
    "ipa": "IPA", "sro": "SRO", "gmpp": "GMPP", "ict": "ICT", "id": "ID",
    "uk": "UK", "eu": "EU", "usd": "USD", "gbp": "GBP", "eur": "EUR",
    "rd": "R&D", "kpi": "KPI", "vat": "VAT", "hr": "HR",
    "q1": "Q1", "q2": "Q2", "q3": "Q3", "q4": "Q4",
}

_TRAILING_STOPWORDS = frozenset({
    "a", "an", "the", "of", "on", "in", "for", "to", "and", "or", "at", "by", "with",
})

# Six words is about what a chart title can spare for one of the columns it
# names, and no business metric needs more to be recognised.
_MAX_WORDS = 6


def derive_label(column: str) -> str:
    """A short, readable label for a raw column name.

    >>> derive_label("financial_year_baseline_currency_m_including_non_government_costs")
    'Financial Year Baseline (M)'
    """
    tokens = [token for token in re.split(r"[^A-Za-z0-9]+", str(column).lower()) if token]
    if not tokens:
        return ""

    tokens, unit = _extract_unit(tokens)
    tokens = _cut_at_qualifier(tokens)
    tokens = _cut_at_repeated_phrase(tokens)
    tokens = tokens[:_MAX_WORDS]
    while tokens and tokens[-1] in _TRAILING_STOPWORDS:
        tokens.pop()
    if not tokens:
        return unit

    label = " ".join(_ACRONYMS.get(token, token.capitalize()) for token in tokens)
    return f"{label} {unit}".strip() if unit else label


def _extract_unit(tokens: list[str]) -> tuple[list[str], str]:
    """Lift a unit out of the name so it can be shown as a suffix."""
    if "pct" in tokens:
        return [token for token in tokens if token != "pct"], "%"
    if "percentage" in tokens:
        return [token for token in tokens if token != "percentage"], "%"
    if "currency" in tokens:
        index = tokens.index("currency")
        rest = tokens[index + 1:]
        if rest and rest[0] == "m":
            return tokens[:index] + rest[1:], "(M)"
        return tokens[:index] + rest, ""
    return tokens, ""


def _cut_at_qualifier(tokens: list[str]) -> list[str]:
    for index, token in enumerate(tokens):
        # Never cut so early that nothing identifying survives.
        if index >= 2 and token in _QUALIFIER_WORDS:
            return tokens[:index]
    return tokens


def _cut_at_repeated_phrase(tokens: list[str]) -> list[str]:
    """Cut before a phrase that repeats.

    Government exports restate the column name inside its own definition:
    "ipa_delivery_confidence_assessment_a_delivery_confidence_assessment_of_..."
    The second "delivery confidence" marks where the name ends and the
    explanation begins.
    """
    seen: dict[tuple[str, str], int] = {}
    for index in range(len(tokens) - 1):
        pair = (tokens[index], tokens[index + 1])
        if pair in seen and index >= 2:
            return tokens[:index]
        seen.setdefault(pair, index)
    return tokens
