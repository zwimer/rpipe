from ..config import UsageError


class VersionError(UsageError):
    """
    Raised when the server has rejected the client version
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
