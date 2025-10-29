from typing import TYPE_CHECKING
from logging import getLogger

from ...shared import DeleteEC
from .errors import ChannelLocked
from .util import request

if TYPE_CHECKING:
    from .data import Config


def delete(conf: Config) -> None:
    """
    Delete the channel
    """
    getLogger("delete").info("Deleting channel %s", conf.channel)
    r = request("DELETE", conf.channel_url(), timeout=conf.timeout)
    if r.status_code == DeleteEC.locked:
        raise ChannelLocked(r.text)
    if not r.ok:
        raise RuntimeError(r)
