from __future__ import annotations
from typing import TYPE_CHECKING
from os import environ
import logging

from zstdlib import Singleton

from .prune_thread import PruneThread
from .state import State

if TYPE_CHECKING:
    from pathlib import Path


class Server(Singleton):

    def __init__(self) -> None:
        self._log = logging.getLogger("server")
        self._debug: bool | None = None
        self.state = State()

    @property
    def debug(self) -> bool:
        if self._debug is None:
            raise RuntimeError("Server not started")
        return self._debug

    def start(self, debug: bool, state_file: Path | None) -> None:
        self._debug = debug
        with self.state as s:
            s.debug = debug
        self._log.info("Initializing server")
        # Load state
        if state_file is not None:
            # Do not run on first load when in debug mode b/c of flask reloader
            if debug and environ.get("WERKZEUG_RUN_MAIN") != "true":
                msg = "State loading and shutdown handling disable on initial flask load on debug mode"
                self._log.info(msg)
            else:
                with self.state as ustate:
                    ustate.load(state_file)
                self.state.install_shutdown_handler(state_file)
        self._log.info("Starting prune thread")
        PruneThread(self.state).start()
        self._log.info("Server initialization complete")
