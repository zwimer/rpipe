from threading import Thread, Condition
from collections import deque
from logging import getLogger
import os


_LOG = "IO"


class IO:
    """
    A better version of stdin.read that doesn't hang as often
    Only meant to ever be used from a single thread at a time
    Will preload about 2n bytes for reading in chunks of <= n
    May use about an extra n bytes for stitching data together
    """

    def __init__(self, fd: int, n: int) -> None:
        self._log = getLogger(_LOG)
        self._log.debug("Constructed IO on fd %d with n=%d", fd, n)
        self._buffer: deque[bytes] = deque()
        self._cond = Condition()
        self._eof: bool = False
        self._fd: int = fd
        self._n: int = n
        self._log.debug("Starting up IO thread.")
        self._thread = Thread(target=self, daemon=True)
        self._thread.start()

    # Main Thread:

    def eof(self) -> bool:
        return self._eof and not self._buffer

    def read(self) -> bytes:
        """
        :param delay: sleep delay ms to allow more IO to load
        :return: Up to n bytes; returns b"" only upon final read
        """
        with self._cond:
            self._cond.wait_for(lambda: self._buffer or self._eof)
            ret: bytes = self._read()
            self._cond.notify()
        self._log.debug("Read %d bytes of data", len(ret))
        return ret

    def _read(self) -> bytes:
        """
        A helper to read that assumes it owns self._buffer
        """
        if not self._buffer:
            return b""
        # Calculate how many pieces to stitch together
        count = 0
        total = 0
        for i in self._buffer:
            total += len(i)
            count += 1
            if total > self._n:
                break
        if len(self._buffer) > 1:
            count -= 1
        assert count > 0, "Write thread wrote too much data"
        # Stitch together pieces as efficiently as possible
        if count == 1:
            return self._buffer.popleft()
        return b"".join(self._buffer.popleft() for _ in range(count))

    # Worker thread

    def __call__(self) -> None:
        until = lambda: sum(len(i) for i in self._buffer) < self._n
        while data := os.read(self._fd, self._n):  # Can read in small bursts
            with self._cond:
                self._cond.wait_for(until)
                self._buffer.append(data)
                self._cond.notify()
        with self._cond:
            self._eof = True
            self._cond.notify()
        self._log.debug("IO has terminated successfully")
