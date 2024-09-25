from logging import WARNING, INFO, DEBUG
from contextlib import contextmanager
import os


LOG_DATEFMT = "%H:%M:%S"
LOG_FORMAT = "%(asctime)s.%(msecs)03d - %(levelname)-8s - %(name)-10s - %(message)s"


_LOG_VERBOSITY: dict[int, int] = {0: WARNING, 1: INFO, 2: DEBUG}


def log_level(verbosity: int) -> int:
    return _LOG_VERBOSITY[max(i for i in _LOG_VERBOSITY if i <= verbosity)]


@contextmanager
def restrict_umask(mask: int):
    old = os.umask(0o66)  # Get the old umask
    try:
        yield os.umask(old | mask)
    finally:
        os.umask(old)
