from __future__ import annotations
from logging import getLogger
from pathlib import Path
import atexit
import signal
import sys

from .save_state import save
from .util import Singleton
from . import globals


_LOG = "ShutdownHandler"


class ShutdownHandler(metaclass=Singleton):
    def __init__(self, dir_: Path):
        self.dir_: Path = dir_
        self._log = getLogger(_LOG)
        self._log.info("Installing signal handlers so that atexit catches these.")
        signal.signal(signal.SIGTERM, lambda *_: sys.exit(1))
        self._log.debug("Installing atexit shutdown handler")
        atexit.register(self._shutdown)

    def _shutdown(self):
        if globals.shutdown:
            return
        globals.shutdown.value = True  # The only place in the program this may be changed
        with globals.lock:
            save(self.dir_)
