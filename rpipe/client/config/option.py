from typing import Generic, TypeVar

_T = TypeVar("_T")


class Option(Generic[_T]):
    def __init__(self, val: _T | None = None) -> None:
        self._value: _T | None = val

    def opt(self, val: _T | None) -> None:
        if self._value is None:
            self._value = val

    @property
    def value(self) -> _T:
        if self._value is None:
            raise RuntimeError("Option value is not set")
        return self._value

    def is_none(self) -> bool:
        return self._value is None

    def is_true(self) -> bool:
        return self._value is True

    def is_false(self) -> bool:
        return self._value is False

    def get(self, default: _T | None = None) -> _T | None:
        return default if self._value is None else self._value
