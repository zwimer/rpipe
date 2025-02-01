from logging import getLogger


class UsageError(ValueError):
    """
    Raised when the user used the client incorrectly (ex. CLI args)
    """

    def __init__(self, msg: str):
        # This is likely CRITICAL, but also likely to be printed out anyway, so log it as info
        getLogger("UsageError").info("%s", msg)
        super().__init__(msg)


class BlockedError(UsageError):
    """
    Raised when the server has blocked this IP address
    """

    def __init__(self) -> None:
        super().__init__("This IP address is blocked by the server")


class VersionError(UsageError):
    """
    Raised when the server has rejected the client version
    """


class ChannelLocked(RuntimeError):
    """
    Raised when attempting to modify a channel is locked
    """


class NoData(ValueError):
    """
    Raised when there is no data available on a channel
    """


class StreamError(RuntimeError):
    """
    Raised when an action fails due to the data being
    streamed in chunks rather than uploaded all at once
    """


class MultipleClients(StreamError):
    """
    Raised when failure occurs due to another user using the same channel
    """


class ReportThis(RuntimeError):
    """
    A RuntimeError that should be reported
    """

    def __init__(self, msg: str):
        super().__init__(f"{msg}\nPlease report this.")
