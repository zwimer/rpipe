from __future__ import annotations
from contextlib import contextmanager
from typing import TYPE_CHECKING
from logging import getLogger

from .util import request, channel_url

if TYPE_CHECKING:
    from ..config import Config


def delete(full_conf: Config) -> None:
    """
    Delete the channel
    """
    getLogger("delete").info("Deleting channel %s", full_conf.channel)
    r = request("DELETE", channel_url(full_conf))
    if not r.ok:
        raise RuntimeError(r)


@contextmanager
def delete_on_fail(config: Config):
    """
    Context manager that deletes the channel on failure
    """
    log = getLogger("DeleteOnFail")
    try:
        yield
    except (KeyboardInterrupt, Exception) as e:
        log.warning("Caught %s; deleting channel", type(e))
        delete(config)
        raise
