"""Column types for Postgres types SQLAlchemy does not ship: `vector(n)` (pgvector) and `regconfig`.

asyncpg has no codec for either, so both travel as text (`'[0.1,0.2]'`, `'german'`); Postgres casts on the way in.
"""

from typing import Any, override

from sqlalchemy.engine.interfaces import Dialect
from sqlalchemy.types import UserDefinedType


class Vector(UserDefinedType[list[float]]):
    """pgvector `vector(dimensions)`; Python value `list[float]`."""

    cache_ok = True

    def __init__(self, dimensions: int) -> None:
        self.dimensions = dimensions

    @override
    def get_col_spec(self, **kw: Any) -> str:
        return f"vector({self.dimensions})"

    @override
    def bind_processor(self, dialect: Dialect) -> Any:
        def process(value: list[float] | None) -> str | None:
            return None if value is None else "[" + ",".join(repr(float(x)) for x in value) + "]"

        return process

    @override
    def result_processor(self, dialect: Dialect, coltype: object) -> Any:
        def process(value: str | None) -> list[float] | None:
            return None if value is None else [float(x) for x in value.strip("[]").split(",") if x]

        return process


class RegConfig(UserDefinedType[str]):
    """Postgres `regconfig` (a text search configuration such as `german`); Python value `str`."""

    cache_ok = True

    @override
    def get_col_spec(self, **kw: Any) -> str:
        return "regconfig"
