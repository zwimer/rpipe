from typing import TYPE_CHECKING, Self
from logging import getLogger

from tqdm.contrib.logging import logging_redirect_tqdm
import tqdm

from .delete import delete
from .data import Result

if TYPE_CHECKING:
    from typing import IO
    from .data import Config, Mode


class Progress:
    """
    A small class to handle progress bars and progression data of send/recv
    """

    DOF_EXC = KeyboardInterrupt | Exception

    __slots__ = ("result", "dof", "_config", "_redir", "_pbar")

    def __init__(self, config: Config, mode: Mode):
        self.result = Result(total=mode.total, checksum=mode.checksum)
        self.dof: bool = False
        self._config = config
        self._redir = logging_redirect_tqdm()
        self._pbar = tqdm.tqdm(
            desc="Uploading" if mode.send else "Downloading",
            disable=not bool(mode.progress),
            # pylint: disable=unidiomatic-typecheck
            total=mode.progress if type(mode.progress) is int else None,
            dynamic_ncols=True,
            leave=False,
            unit_divisor=1000,
            unit_scale=True,
            unit="B",
        )

    def __enter__(self) -> Self:
        self._redir.__enter__()
        self._pbar.__enter__()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.dof and isinstance(exc_val, self.DOF_EXC):
            log = getLogger("Progress")
            log.warning("Caught %s. Deleting channel: %s", type(exc_val), self._config.channel)
            delete(self._config)
        r1 = bool(self._pbar.__exit__(exc_type, exc_val, exc_tb))
        r2 = bool(self._redir.__exit__(exc_type, exc_val, exc_tb))
        return r1 or r2

    def update(self, data: bytes, *, file: IO[bytes] | None = None) -> None:
        self.dof = True
        self._pbar.update(len(data))
        if self.result.total is not None:
            self.result.total += len(data)
        if self.result.checksum is not None:
            self.result.checksum.update(data)
        if file is not None:
            file.write(data)
            file.flush()
