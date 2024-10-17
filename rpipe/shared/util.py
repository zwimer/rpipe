from __future__ import annotations
from contextlib import contextmanager
from typing import TYPE_CHECKING
from os import umask

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
