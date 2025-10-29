from functools import total_ordering

from .. import __version__


@total_ordering
class Version:
    """
    A class to represent a version number
    Implements comparison, equality, and str operators
    Allows invalid versions but marks them as such
    """

    _invalid = (-1, -1, -1)
    _invalid_str = "Unable to parse version"

    def __init__(self, v: str | bytes):
        try:
            self.str: str = v if isinstance(v, str) else v.decode()
            tup = tuple(int(i) for i in self.str.split("."))
            self.tuple = tup if len(tup) == 3 else self._invalid
        except ValueError:
            self.str = self._invalid_str
            self.tuple = self._invalid

    def invalid(self) -> bool:
        return self.tuple == self._invalid

    def __str__(self) -> str:
        return self.str

    def __bytes__(self):
        return str(self).encode()

    def __lt__(self, other: Version):
        return self.tuple < other.tuple

    def __eq__(self, other: object):
        return isinstance(other, Version) and self.str == other.str


version = Version(__version__)

WEB_VERSION = Version("0.0.0")
assert not WEB_VERSION.invalid()  # nosec B101
