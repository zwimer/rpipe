from threading import RLock
from .data import Stream


streams: dict[str, Stream] = {}
lock = RLock()
