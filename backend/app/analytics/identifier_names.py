"""Recognise explicit identifier names without changing their recorded values."""
from __future__ import annotations

import re

_MARKERS = {"id", "key", "code", "uuid", "guid"}
_COMPACT_ENTITY = re.compile(
    r"(?:employee|staff|customer|client|patient|donor|student|member|user|account|"
    r"order|invoice|shipment|product|supplier|vendor|booking|flight|policy|claim|"
    r"transaction|ticket|asset|application|assessment|module|presentation)"
    r"(?:id|key|code|uuid|guid|number|num|no)"
)


def canonical_identifier_name(name: str) -> str | None:
    """Match id_student with student_id while keeping different marker kinds."""
    text = str(name).strip()
    if text.endswith("#"):
        text = text[:-1] + "_id"
    text = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", text)
    text = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", text)
    words = re.findall(r"[a-z0-9]+", text.lower())
    # Cleaning and joins append a disambiguation number or a related suffix.
    if words and words[-1].isdigit():
        words.pop()
    if words and words[-1] == "related":
        words.pop()
    if not words or words[:2] == ["number", "of"] or words[-1] == "count":
        return None
    if words[0] in _MARKERS:
        return "".join([*words[1:], words[0]])
    if words[-1] in _MARKERS:
        return "".join(words)
    compact = "".join(words)
    return compact if _COMPACT_ENTITY.fullmatch(compact) else None
