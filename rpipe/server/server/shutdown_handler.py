from __future__ import annotations
from typing import TYPE_CHECKING
from logging import getLogger
from pathlib import Path
import atexit
import signal
import sys

from ..util import Singleton

if TYPE_CHECKING:
    from .state import State


_LOG = "ShutdownHandler"


class ShutdownHandler(metaclass=Singleton):
    def __init__(self, state: State, file: Path):
        self._state = state
        self.file: Path = file
        self._log = getLogger(_LOG)
        self._log.info("Installing signal handlers so that atexit catches these.")
        signal.signal(signal.SIGTERM, lambda *_: sys.exit(1))
        self._log.info("Installing atexit shutdown handler")
        atexit.register(self._shutdown)

    def _shutdown(self):
        self._log.critical("Server shutdown initiated")
        with self._state as state:
            state.shutdown = True
            state.save(self.file)
