from zstdlib import Enum


BLOCKED_EC: int = 401


# pylint: disable=bad-mcs-method-argument,bad-mcs-classmethod-argument
class UploadEC(Enum):
    """
    HTTP error codes the rpipe client may be sent when uploading data
    Others may be sent, but these are the ones the client should be prepared to handle
    """

    wrong_version: int = 412  #    PUT: different version than initial POST
    illegal_version: int = 426  #  Illegal version
    stream_id: int = 422  #        POST: Has stream ID, should not; PUT: missing stream ID
    too_big: int = 413  #          Too much data sent to server
    conflict: int = 409  #         Stream ID indicates a different stream than exists
    wait: int = 425  #             Try again in a bit, waiting on the other end of the pipe
    forbidden: int = 406  #        Writing to finalized stream
    locked: int = 423  #           Channel is locked and cannot be edited


class DownloadEC(Enum):
    """
    HTTP error codes the rpipe client may be sent when downloading data
    Others may be sent, but these are the ones the client should be prepared to handle
    """

    wrong_version: int = 412  #    GET: bad version
    illegal_version: int = 426  #  Illegal version
    no_data: int = 410  #          No data on this channel; takes priority over stream_id error
    conflict: int = 409  #         Stream ID indicates a different stream than exists
    wait: int = 425  #             Try again in a bit, waiting on the other end of the pipe
    forbidden: int = 406  #        StreamID passed for new stream or while peeking
    cannot_peek: int = 452  #      Cannot peek, too much data
    in_use: int = 453  #           Someone else is reading from the pipe
    locked: int = 423  #           Channel is locked and cannot be edited


class DeleteEC(Enum):
    """
    HTTP error codes the rpipe client may be sent when deleting a channel
    Others may be sent, but these are the ones the client should be prepared to handle
    """

    locked: int = 423  #           Channel is locked and cannot be edited


class QueryEC(Enum):
    """
    HTTP error codes the rpipe client may be sent when in query mode
    Others may be sent, but these are the ones the client should be prepared to handle
    """

    illegal_version: int = 426  #  Illegal version
    no_data: int = 410  #          No data on this channel


class AdminEC(Enum):
    """
    HTTP error codes the rpipe client may be sent when in admin mode
    Others may be sent, but these are the ones the client should be prepared to handle
    """

    invalid: int = 400
    unauthorized: int = 403
    illegal_version: int = 426
