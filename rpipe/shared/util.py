from __future__ import annotations
from tempfile import NamedTemporaryFile
from contextlib import contextmanager
from typing import TYPE_CHECKING
from logging import getLogger
from atexit import register
from pathlib import Path
from os import umask

from flask import request

if TYPE_CHECKING:
    from collections.abc import Sequence


_LOG = "util"


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


def _unlink(p: Path) -> None:
    if p.exists(follow_symlinks=False):
        getLogger(_LOG).debug("Removing: %s", p)
        p.unlink()


def mk_temp_f(**kwargs) -> Path:
    """
    Create a NamedTemporaryFile with an atexit handler to purge it
    """
    log = getLogger(_LOG)
    with NamedTemporaryFile(**kwargs, delete=False) as f:
        ret = Path(f.name)
    log.debug("Created temporary file: %s", ret)
    register(_unlink, ret)
    return ret
