from __future__ import annotations
from typing import TYPE_CHECKING
from logging import getLogger

from .util import request, channel_url

if TYPE_CHECKING:
    from ..config import Config


def clear(full_conf: Config) -> None:
    """
    Clear the channel
    """
    getLogger("clear").info("Clearing channel %s", full_conf.channel)
    r = request("DELETE", channel_url(full_conf))
    if not r.ok:
        raise RuntimeError(r)
