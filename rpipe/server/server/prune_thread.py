from typing import TYPE_CHECKING
from logging import getLogger
from threading import Thread
from time import sleep

from ...shared import TRACE

if TYPE_CHECKING:
    from .state import State


class PruneThread(Thread):
    """
    A thread class that periodically prunes expired pipes from the server
    """

    def __init__(self, state: State):
        super().__init__(target=self._periodic_prune, daemon=True)
        self._state: State = state

    def _periodic_prune(self) -> None:
        log = getLogger("Prune Thread")
        log.info("Starting prune loop")
        while True:
            log.log(TRACE, "Acquiring state lock")
            with self._state as rw_state:
                if rw_state.shutdown:
                    log.debug("Quitting, state is shutdown")
                    return
                log.log(TRACE, "Checking for expired streams")
                expired = [i for i, k in rw_state.streams.items() if k.expired()]
                log.log(TRACE, "Pruning %d expired streams", len(expired))
                for i in expired:
                    log.info("Pruning expired channel %s", i)
                    del rw_state.streams[i]
            log.log(TRACE, "Sleeping for 5 seconds")
            sleep(5)  # Wait a few seconds before checking again
