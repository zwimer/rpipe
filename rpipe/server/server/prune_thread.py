from __future__ import annotations
from typing import TYPE_CHECKING
from logging import getLogger
from threading import Thread
from time import sleep

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
            with self._state as rw_state:
                if rw_state.shutdown:
                    return
                expired = []
                for i, k in rw_state.streams.items():
                    if k.expired():
                        log.info("Pruning expired channel %s", i)
                        expired.append(i)
                for i in expired:
                    del rw_state.streams[i]
            sleep(5)  # Wait a few seconds before checking again
