from __future__ import annotations
from logging import WARNING, INFO, DEBUG
from contextlib import contextmanager
from typing import TYPE_CHECKING
from os import umask

from human_readable import file_size

if TYPE_CHECKING:
    from collections.abc import Sequence


LOG_DATEFMT = "%H:%M:%S"
LOG_FORMAT = "%(asctime)s.%(msecs)03d - %(levelname)-8s - %(name)-10s - %(message)s"


_LOG_VERBOSITY: dict[int, int] = {0: WARNING, 1: INFO, 2: DEBUG}


class LFS:
    """
    Human-readable number of bytes, lazily evaluated for logging
    """

    def __init__(self, x: int | bytes) -> None:
        self._x: int = x if isinstance(x, int) else len(x)

    def __str__(self) -> str:
        return file_size(self._x)


def log_level(verbosity: int) -> int:
    return _LOG_VERBOSITY[max(i for i in _LOG_VERBOSITY if i <= verbosity)]


def total_len(x: Sequence[bytes]) -> int:
    return sum(len(i) for i in x)


@contextmanager
def restrict_umask(mask: int):
    old = umask(0o66)  # Get the old umask
    try:
        yield umask(old | mask)
    finally:
        umask(old)
