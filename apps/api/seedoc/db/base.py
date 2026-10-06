"""Declarative base with the constraint naming convention from docs/DATA_MODEL.md §6."""

from datetime import datetime
from enum import Enum
from typing import Any, ClassVar

from sqlalchemy import DateTime, MetaData, Text
from sqlalchemy.dialects.postgresql import ENUM
from sqlalchemy.orm import DeclarativeBase

NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

metadata = MetaData(naming_convention=NAMING_CONVENTION)


def pg_enum(enum_type: type[Enum], name: str, **kwargs: Any) -> ENUM:
    def _values(e: type[Enum]) -> list[str]:
        return [str(m.value) for m in e]

    return ENUM(enum_type, name=name, values_callable=_values, **kwargs)


class Base(DeclarativeBase):
    metadata = metadata
    type_annotation_map: ClassVar[dict[Any, Any]] = {
        datetime: DateTime(timezone=True),
        str: Text,
    }
