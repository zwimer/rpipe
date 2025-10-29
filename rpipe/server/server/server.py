from typing import TYPE_CHECKING
from logging import getLogger
import signal
import atexit

from werkzeug.serving import is_running_from_reloader
from zstdlib import Singleton


from .prune_thread import PruneThread
from .state import State

if TYPE_CHECKING:
    from pathlib import Path


_LOG = "Server"


def _ctrlc(sig, *_):
    getLogger(_LOG).error("Received signal %s; raising KeyboardInterrupt", sig)
    raise KeyboardInterrupt()


class Server(Singleton):
    """
    The main server class
    This class is a singleton and should only be instantiated once
    This class is responsible for initializing the server and handling shutdown
    This class may install signal handlers for signal.SIGNALS so that atexit catches them
    """

    SIGNALS = (signal.SIGINT, signal.SIGTERM, signal.SIGQUIT)
    __slots__ = ("state", "_state_file", "_log")

    def shutdown(self):
        """
        Shut the server down
        """
        log = getLogger(_LOG)
        log.critical("Server shutdown initiated")
        with self.state as u:
            if u.shutdown:
                raise RuntimeError("Server already shut down")
            u.shutdown = True
            log.info("Removing atexit shutdown registration")
            atexit.unregister(self.shutdown)
            if self._state_file is not None:
                u.save(self._state_file)
                return
        log.warning("State file not set; state will not be saved")

    def __init__(self, debug: bool, state_file: Path | None) -> None:
        self._log = getLogger(_LOG)
        self._log.info("Initializing server")
        self._state_file: Path | None = state_file
        self.state = State(debug)
        # Flask reloader will just relaunch this so we skip most configuration (such as persistent items)
        if debug and not is_running_from_reloader():
            # It is important not to catch signals in the reloader process
            # It will fail to detect the death of its children and hang
            self._log.info("Skipping initialization until reload")
            return
        if not debug:  # Don't do this for debug, it will be overridden
            self._log.info("Installing signal handlers to ensure graceful shutdown")
            for i in self.SIGNALS:
                signal.signal(i, _ctrlc)
        # Load state file as needed
        if self._state_file is not None:
            with self.state as u:
                u.load(self._state_file)
        # Start prune thread
        self._log.info("Starting prune thread")
        PruneThread(self.state).start()
        # Ensure state is saved on exit
        self._log.info("Installing atexit shutdown handler for state saving")
        atexit.register(self.shutdown)
        self._log.info("Server initialization complete")
