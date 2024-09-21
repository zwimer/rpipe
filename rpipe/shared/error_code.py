from enum import Enum, unique


@unique
class UploadErrorCode(Enum):
    """
    HTTP error codes the rpipe client may be sent when uploading data
    """

    wrong_version: int = 412  #    PUT: different version than initial POST
    illegal_version: int = 426  #  Illegal version
    stream_id: int = 422  #        POST: Has stream ID, should not; PUT: missing stream ID
    too_big: int = 413  #          Too much data sent to server
    conflict: int = 409  #         Stream ID indicates a different stream than exists
    wait: int = 425  #             Try again in a bit, waiting on the other end of the pipe
    forbidden: int = 403  #        Writing to finalized stream


@unique
class DownloadErrorCode(Enum):
    """
    HTTP error codes the rpipe client may be sent when downloading data
    """

    wrong_version: int = 412  #    GET: bad version
    illegal_version: int = 426  #  Illegal version
    no_data: int = 410  #          No data on this channel; takes priority over stream_id error
    conflict: int = 409  #         Stream ID indicates a different stream than exists
    wait: int = 425  #             Try again in a bit, waiting on the other end of the pipe
    forbidden: int = 403  #        StreamID passed for new stream or while peeking
    cannot_peek: int = 452  #      Cannot peek, too much data
    in_use: int = 453  #           Someone else is reading from the pipe
