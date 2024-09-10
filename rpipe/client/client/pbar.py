from __future__ import annotations
from dataclasses import dataclass
from typing import TYPE_CHECKING
import sys

from tqdm.contrib.logging import logging_redirect_tqdm
import tqdm

if TYPE_CHECKING:
    from contextlib import _GeneratorContextManager


@dataclass(frozen=True, kw_only=True)
class _Wraps:
    tqdm: tqdm.std.tqdm
    redirect: _GeneratorContextManager


class PBar:
    """
    A small tqdm wrapper that is only enabled when requested
    """

    def __init__(self, progress: bool | int):
        self.total: int | None = None if isinstance(progress, bool) else progress
        self.enable = progress is not False
        self._wraps: _Wraps | None = None

    def __enter__(self):
        if self.enable:
            real = tqdm.tqdm(
                total=self.total,
                dynamic_ncols=True,
                leave=False,
                unit_divisor=1000,
                unit_scale=True,
                unit="B",
            )
            self._wraps = _Wraps(tqdm=real, redirect=logging_redirect_tqdm())
            self._wraps.redirect.__enter__()
            self._wraps.tqdm.__enter__()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if not self.enable:
            return
        if self._wraps is None:
            raise RuntimeError("PBar not entered")
        try:
            args = (exc_type, exc_val, exc_tb)
            self._wraps.tqdm.__exit__(*args)
        except:  # pylint: disable=bare-except # noqa: E722
            args = sys.exc_info()
        self._wraps.redirect.__exit__(*args)

    def update(self, n: int):
        if self.enable:
            if self._wraps is None:
                raise RuntimeError("PBar not entered")
            self._wraps.tqdm.update(n)
