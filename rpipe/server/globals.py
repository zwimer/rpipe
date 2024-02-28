from threading import RLock
from .data import Stream

from .util import Boolean

streams: dict[str, Stream] = {}
lock = RLock()
shutdown = Boolean(False)
