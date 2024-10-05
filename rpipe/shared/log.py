from logging import WARNING, INFO, DEBUG
import logging

from human_readable import file_size

from .util import total_len


DATEFMT = "%H:%M:%S"
FORMAT = "%(asctime)s.%(msecs)03d - %(levelname)-8s - %(name)-10s - %(message)s"

TRACE = DEBUG - 5
assert TRACE > 0
_VERBOSITY: dict[int, int] = {0: WARNING, 1: INFO, 2: DEBUG, 3: TRACE}


class LFS:
    """
    Human-readable number of bytes, lazily evaluated for logging
    """

    def __init__(self, x: int | bytes | list[bytes]) -> None:
        self._x = x if isinstance(x, int) else (total_len(x) if isinstance(x, list) else len(x))

    def __str__(self) -> str:
        return file_size(self._x)


def level(verbosity: int) -> int:
    return _VERBOSITY[max(i for i in _VERBOSITY if i <= verbosity)]


def define_trace():
    """
    Add a TRACE level to the logging module
    """
    assert not hasattr(logging, "TRACE"), "Already added TRACE level"
    logging.addLevelName(TRACE, "TRACE")
