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

    def __init__(self, debug: bool, state_file: Path | None) -> None:
        log = logging.getLogger("server")
        self.state = State()
        with self.state as s:
            s.debug = debug
        log.info("Initializing server")
        # Load state
        if state_file is not None:
            # Do not run on first load when in debug mode b/c of flask reloader
            if debug and environ.get("WERKZEUG_RUN_MAIN") != "true":
                msg = "State loading and shutdown handling disable on initial flask load on debug mode"
                log.info(msg)
            else:
                with self.state as ustate:
                    ustate.load(state_file)
                self.state.install_shutdown_handler(state_file)
        log.info("Starting prune thread")
        PruneThread(self.state).start()
        log.info("Server initialization complete")
