from logging import WARNING, INFO, DEBUG
import logging

from human_readable import file_size


DATEFMT = "%H:%M:%S"
FORMAT = "%(asctime)s.%(msecs)03d - %(levelname)-8s - %(name)-10s - %(message)s"

_TRACE = DEBUG - 5
assert _TRACE > 0
_VERBOSITY: dict[int, int] = {0: WARNING, 1: INFO, 2: DEBUG, 3: _TRACE}


class LFS:
    """
    Human-readable number of bytes, lazily evaluated for logging
    """

    def __init__(self, x: int | bytes) -> None:
        self._x: int = x if isinstance(x, int) else len(x)

    def __str__(self) -> str:
        return file_size(self._x)


def level(verbosity: int) -> int:
    return _VERBOSITY[max(i for i in _VERBOSITY if i <= verbosity)]


def define_trace():
    """
    Add a TRACE level to the logging module
    """
    assert not hasattr(logging, "TRACE"), "Already added TRACE level"
    logging.TRACE = _TRACE
    logging.addLevelName(logging.TRACE, "TRACE")
    logging.trace = lambda *args, **kwargs: logging.log(logging.TRACE, *args, **kwargs)
    logging.getLoggerClass().trace = lambda self, *args, **kwargs: self.log(logging.TRACE, *args, **kwargs)
