from __future__ import annotations


__version__: str = "5.5.1"  # Must be "<major>.<minor>.<patch>", all numbers


class Version:
    _invalid = (-1, -1, -1)

    def __init__(self, v: str):
        self.str = v
        try:
            tup = tuple(int(i) for i in self.str.split("."))
            self.tuple = tup if len(tup) == 3 else self._invalid
        except ValueError:
            self.tuple = self._invalid

    def invalid(self) -> bool:
        return self.tuple == self._invalid

    def __str__(self) -> str:
        return self.str

    def __lt__(self, other: Version):
        return self.tuple < other.tuple

    def __eq__(self, other: object):
        return isinstance(other, Version) and self.str == other.str


version = Version(__version__)
