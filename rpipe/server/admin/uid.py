from datetime import datetime, timedelta
from logging import getLogger
from threading import RLock
from os import urandom


class UID:
    """
    A class to manage UIDs that are used for signature verification
    """

    _UID_EXPIRE: int = 300
    _UID_LEN: int = 32

    def __init__(self) -> None:
        self._uids: dict[str, datetime] = {}
        self._log = getLogger("UID")
        self._lock = RLock()

    def new(self, n: int) -> list[str]:
        ret = [urandom(self._UID_LEN).hex() for i in range(n)]
        with self._lock:
            eol = datetime.now() + timedelta(seconds=self._UID_EXPIRE)
            self._uids.update({i: eol for i in ret})
        self._log.debug("Generated %s new UIDs", n)
        return ret

    def verify(self, uid: str) -> bool:
        self._log.debug("Verifying UID: %s", uid)
        with self._lock:
            if uid not in self._uids:
                self._log.error("UID not found: %s", uid)
                return False
            if datetime.now() > self._uids.pop(uid):
                self._log.warning("UID expired: %s", uid)
                return False
            self._log.debug("UID verified")
        return True
