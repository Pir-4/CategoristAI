from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import inspect


class BaseModel(DeclarativeBase):
    def __repr__(self) -> str:
        state = inspect(self)
        fields = ", ".join(
            f"{attr.key}={getattr(self, attr.key)!r}"
            for attr in state.mapper.column_attrs
        )
        return f"{self.__class__.__name__}({fields})"
