"""Bounded, owner-supplied descriptions of original source fields."""
from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictFloat,
    StrictInt,
    StrictStr,
    field_validator,
    model_validator,
)

MAX_DICTIONARY_BYTES = 1_048_576


class DictionaryModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, str_strip_whitespace=False)


class DefinitionSource(DictionaryModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    url: str | None = Field(default=None, min_length=1, max_length=2048)
    version: str | None = Field(default=None, min_length=1, max_length=200)
    sha256: str | None = Field(default=None, pattern=r"^[a-fA-F0-9]{64}$")

    @field_validator("url")
    @classmethod
    def public_source_url(cls, value: str | None) -> str | None:
        from urllib.parse import urlsplit

        if value is not None:
            parsed = urlsplit(value)
            if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
                raise ValueError("A source link must be an http or https address without login details.")
        return value


class ValueDefinition(DictionaryModel):
    value: StrictStr | StrictInt | StrictFloat | StrictBool | None
    label: str = Field(min_length=1, max_length=80)
    description: str | None = Field(default=None, min_length=1, max_length=1000)

    @field_validator("label", "description")
    @classmethod
    def readable_text(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("A label or explanation must contain readable text.")
        return value.strip() if value is not None else value

    @field_validator("value")
    @classmethod
    def bounded_value(cls, value: Any) -> Any:
        if isinstance(value, str) and len(value) > 256:
            raise ValueError("A code can contain at most 256 characters.")
        return value


class RelativeDayBasis(DictionaryModel):
    kind: Literal["relative_day"]
    origin: str = Field(min_length=1, max_length=200)

    @field_validator("origin")
    @classmethod
    def meaningful_origin(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Describe the starting point for the day count.")
        return value.strip()


class FieldDefinition(DictionaryModel):
    source_table: str = Field(min_length=1, max_length=255)
    source_sheet: str | None = Field(default=None, min_length=1, max_length=255)
    source_column: str = Field(min_length=1, max_length=512)
    source_role: str | None = Field(default=None, min_length=1, max_length=255)
    label: str | None = Field(default=None, min_length=1, max_length=80)
    description: str | None = Field(default=None, min_length=1, max_length=1000)
    values: list[ValueDefinition] = Field(default_factory=list, max_length=500)
    unit: str | None = Field(default=None, min_length=1, max_length=64)
    time_basis: RelativeDayBasis | None = None
    source: DefinitionSource | None = None

    @field_validator("label", "description", "unit")
    @classmethod
    def readable_text(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("A label, explanation or unit must contain readable text.")
        return value.strip() if value is not None else value

    @field_validator("source_table")
    @classmethod
    def original_basename(cls, value: str) -> str:
        if "/" in value or "\\" in value or value in {".", ".."}:
            raise ValueError("Use the original file name, without a folder path.")
        return value

    @model_validator(mode="after")
    def has_definition(self) -> FieldDefinition:
        if not any((self.label, self.description, self.values, self.unit, self.time_basis)):
            raise ValueError("Provide a label, explanation, code meaning, unit or relative-day origin.")
        return self


class DataDictionary(DictionaryModel):
    version: Literal[1]
    fields: list[FieldDefinition] = Field(min_length=1, max_length=200)

    @model_validator(mode="before")
    @classmethod
    def bounded_document(cls, value: Any) -> Any:
        if isinstance(value, dict) and type(value.get("version")) is not int:
            raise ValueError("The data guide version must be the integer 1.")
        try:
            size = len(json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8"))
        except (TypeError, ValueError) as exc:
            raise ValueError("The data guide must contain ordinary JSON values.") from exc
        if size > MAX_DICTIONARY_BYTES:
            raise ValueError("The data guide must be no larger than 1 MiB.")
        return value


def validate_dictionary_context(context: dict[str, Any] | None) -> dict[str, Any] | None:
    if context is None or "data_dictionary" not in context:
        return context
    dictionary = DataDictionary.model_validate(context["data_dictionary"])
    return {**context, "data_dictionary": dictionary.model_dump(mode="json")}
