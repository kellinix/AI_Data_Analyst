from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import DeclarativeBase, declared_attr


class Base(AsyncAttrs, DeclarativeBase):
    """Base class for all SQLAlchemy models."""

    @declared_attr.directive
    def __tablename__(cls) -> str:
        """Auto-generate table names from class names (snake_case plural)."""
        name = cls.__name__
        # Convert CamelCase to snake_case
        result = [name[0].lower()]
        for char in name[1:]:
            if char.isupper():
                result.extend(["_", char.lower()])
            else:
                result.append(char)
        return "".join(result) + "s"
