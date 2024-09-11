from threading import Thread, Condition, get_ident
from collections import deque
from logging import getLogger
import os


class IO:
    """
    A better version of stdin.read that doesn't hang as often
    Only meant to ever be used from a single thread at a time
    Will attempt to keep chunk bytes loaded at all times, may
    preload 2*chunk bytes to do so. Optimal chunk read size is chunk
    May use about an extra chunk bytes for stitching data together
    """

    def __init__(self, fd: int, chunk: int) -> None:
        """
        :param fd: The file descriptor to read from
        :param chunk: The number of bytes to keep preloaded whenever possible
        """
        self._thread = Thread(target=self, daemon=True)  # Construct first
        self._log.info("Constructed IO on fd %d with chunk size: %d", fd, chunk)
        self._buffer: deque[bytes] = deque()
        self._cond = Condition()
        self._eof: bool = False
        self._fd: int = fd
        self._chunk: int = chunk
        self._log.info("Starting up IO thread.")
        self._thread.start()

    @property
    def _log(self):
        """
        Return the logger for the current thread
        self._thread must exist
        """
        return getLogger("IO Thread" if get_ident() == self._thread.ident else "IO Main")

    # Main Thread

    def read(self, n: int | None = None) -> bytes:
        """
        :param n: The maximum number of bytes to read; if None read the chunk size
        :return: Up to n bytes; returns b"" only upon final read
        """
        with self._cond:
            self._cond.wait_for(lambda: self._buffer or self._eof)
            ret: bytes = self._read(self._chunk if n is None else n)
            self._cond.notify()
        if ret:
            self._log.debug("Read %d bytes of data", len(ret))
            return ret
        self._log.info("Read EOF")
        return b""

    def _read(self, n: int) -> bytes:
        """
        A helper to read that assumes it owns self._buffer
        Optimal read size is self._chunk
        :param n: The maximum number of bytes to read
        """
        if not self._buffer:
            return b""
        # Calculate how many pieces to stitch together
        count: int = 0
        total: int = 0
        for i in self._buffer:
            total += len(i)
            count += 1
            if total > n:
                break
        if len(self._buffer) > 1:  # To avoid going over n bytes
            count -= 1
        # Stitch together pieces as efficiently as possible
        if count == 0:  # This is slow, read size is too small
            ret = self._buffer[0][:n]
            self._buffer[0] = self._buffer[0][n:]
            return ret
        if count == 1:
            return self._buffer.popleft()
        return b"".join(self._buffer.popleft() for _ in range(count))

    # Worker thread

    def __call__(self) -> None:
        """
        The worker thread that reads data from the file descriptor
        Always attempts to keep at least self._chunk bytes loaded
        """
        until = lambda: sum(len(i) for i in self._buffer) < self._chunk
        while data := os.read(self._fd, self._chunk):  # Can read in small bursts
            with self._cond:
                self._cond.wait_for(until)
                self._buffer.append(data)
                self._cond.notify()
            self._log.debug("Loaded %d bytes of data from input", len(data))
        # EOF
        with self._cond:
            self._eof = True
            self._cond.notify()
        self._log.info("Data loading complete. IO thread terminating.")
