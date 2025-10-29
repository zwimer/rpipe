from tempfile import SpooledTemporaryFile
from contextlib import contextmanager
from typing import TYPE_CHECKING
from logging import getLogger
from os import umask

from psutil import virtual_memory
from flask import request

if TYPE_CHECKING:
    from collections.abc import Sequence


def remote_addr() -> str:
    addr = request.remote_addr
    xf = request.headers.get("X-Forwarded-For")
    return f"{addr} / X-Forwarded-For: {xf}" if xf else str(addr)


def total_len(x: Sequence[bytes]) -> int:
    return sum(len(i) for i in x)


@contextmanager
def restrict_umask(mask: int):
    old = umask(0o66)  # Get the old umask
    try:
        yield umask(old | mask)
    finally:
        umask(old)


class SpooledTempFile(SpooledTemporaryFile):
    """
    A subclass of SpooledTemporaryFile that provides a
    method of checking if the files is fully in memory
    """

    _log = "TempFile"

    def __init__(self) -> None:
        n = virtual_memory().available
        getLogger(self._log).debug("Initializing in memory with max_size=%d", n)
        super().__init__(n)
        self._is_virtual: bool = True  # self._rolled is private so we use this instead

    @property
    def is_virtual(self) -> bool:
        """
        :return: True if the file is spooled / contained entirely in memory
        """
        return self._is_virtual

    def rollover(self) -> None:
        if self._is_virtual:
            log = getLogger(self._log)
            log.info("max_size exceeded; rolling onto disk")
            super().rollover()
            log.debug("Rollover complete")
        self._is_virtual = False
