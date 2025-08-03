from threading import Thread, Condition
from logging import getLogger
import os

from ...shared import TRACE, LFS, SpooledTempFile, total_len


class IO:
    """
    A better version of stdin.read that doesn't hang as often
    Only meant to ever be used from a single thread at a time
    Will attempt to keep chunk bytes loaded at all times
    May use about an extra chunk bytes for stitching data together
    """

    __slots__ = ("_mlog", "_buffer", "_cond", "_eof", "_chunk", "_fd")

    def __init__(self, fd: int | SpooledTempFile, chunk: int) -> None:
        """
        :param fd: The file descriptor (or SpooledTemporaryFile) to read from
        :param chunk: The number of bytes to keep preloaded whenever possible
        """
        if isinstance(fd, SpooledTempFile) and not fd.is_virtual:
            fd = fd.fileno()  # This is a file on disk, so prefer reading as such
        self._fd: int | SpooledTempFile = fd
        self._mlog = getLogger("IO Main")
        self._buffer: list[bytes] = []
        self._cond = Condition()
        self._eof: bool = False  # Set when reader *thread* hits EOF; _buffer may still have data
        self._chunk: int = chunk
        if isinstance(self._fd, int):  # No need when reading from RAM
            self._mlog.info("Starting IO thread on fd %d with chunk size: %s", self._fd, LFS(self._chunk))
            Thread(target=self._worker, daemon=True).start()

    # Main Thread

    def increase_chunk(self, n: int) -> None:
        """
        Increase the chunk size to n bytes
        """
        if n < self._chunk:
            raise ValueError("Cannot decrease chunk size")
        if n != self._chunk:
            self._mlog.info("Updating IO chunk size to %s", LFS(n))
            with self._cond:
                self._chunk = n
                self._cond.notify()

    def read(self) -> tuple[bytes, bool]:
        """
        Read up to self._chunk bytes; b"" only if EOF
        :return: A tuple containing the bytes read and a boolean indicating EOF
        """
        with self._cond:
            if isinstance(self._fd, SpooledTempFile):
                return (ret := self._fd.read(self._chunk)), len(ret) == 0
            # If fd is a file descriptor
            self._cond.wait_for(lambda: self._buffer or self._eof)
            ret = b"".join(self._buffer)
            assert len(ret) <= self._chunk, "Sanity check failed"
            self._buffer.clear()
            self._cond.notify()
        if ret:
            self._mlog.debug("Read %s bytes of data", LFS(ret))
        return ret, self._eof and not self._buffer

    # Worker thread (only exists if fd is int)

    def _worker(self) -> None:
        """
        The worker thread that reads data from the file descriptor
        Always attempts to keep at least self._chunk bytes loaded
        """
        assert isinstance(self._fd, int), "Sanity check"
        log = getLogger("IO Thread")
        n = self._chunk
        until = lambda: total_len(self._buffer) < self._chunk
        # os.read may read in small chunks (ex. pipe buffer capacity in Linux)
        while data := os.read(self._fd, n):
            log.log(TRACE, "Loaded %s bytes of data from input", LFS(data))  # This can be spammy, so trace
            with self._cond:
                self._buffer.append(data)
                self._cond.notify()
                self._cond.wait_for(until)
                n = self._chunk - total_len(self._buffer)
        with self._cond:
            self._eof = True
            self._cond.notify()
        log.info("Read EOF. IO thread terminating.")
