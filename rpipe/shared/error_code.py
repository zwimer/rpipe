# Note that we don't use real enums in this file for multiple reasons
# One of which is that these enums are incomplete and other error codes exist
# Enum just adds extra overhead and code bloat


# pylint: disable=bad-mcs-method-argument,bad-mcs-classmethod-argument
class _UniqueEnum(type):
    """
    Metaclass for 'Enum' classes to ensure that their values are unique and the class is never instantiated
    """

    def __new__(mcls, name, bases, attrs, **kwargs):
        def _ni(*_, **__):
            raise NotImplementedError("Cannot instantiate this class")

        for bad in ("__init__", "__new__"):
            if bad in attrs:
                raise ValueError("Cannot define __init__ or __new__")
            attrs[bad] = _ni
        values = set()
        for v in (k for i, k in attrs.items() if not i.startswith("__")):
            if v in values:
                raise ValueError(f"Duplicate value: {v}")
            if not isinstance(v, int):
                raise ValueError(f"Value must be an int: {v}")
            values.add(v)
        return type.__new__(mcls, name, bases, attrs, **kwargs)

    def __delattr__(self, *_):
        raise AttributeError("Cannot modify this class")

    def __setattr__(self, *_):
        raise AttributeError("Cannot modify this class")


class UploadEC(metaclass=_UniqueEnum):
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
    forbidden: int = 403  #        Writing to finalized stream


class DownloadEC(metaclass=_UniqueEnum):
    """
    HTTP error codes the rpipe client may be sent when downloading data
    Others may be sent, but these are the ones the client should be prepared to handle
    """

    wrong_version: int = 412  #    GET: bad version
    illegal_version: int = 426  #  Illegal version
    no_data: int = 410  #          No data on this channel; takes priority over stream_id error
    conflict: int = 409  #         Stream ID indicates a different stream than exists
    wait: int = 425  #             Try again in a bit, waiting on the other end of the pipe
    forbidden: int = 403  #        StreamID passed for new stream or while peeking
    cannot_peek: int = 452  #      Cannot peek, too much data
    in_use: int = 453  #           Someone else is reading from the pipe


class QueryEC(metaclass=_UniqueEnum):
    """
    HTTP error codes the rpipe client may be sent when in query mode
    Others may be sent, but these are the ones the client should be prepared to handle
    """

    illegal_version: int = 426  #  Illegal version
    no_data: int = 410  #          No data on this channel


class AdminEC(metaclass=_UniqueEnum):
    """
    HTTP error codes the rpipe client may be sent when in admin mode
    Others may be sent, but these are the ones the client should be prepared to handle
    """

    invalid: int = 400
    unauthorized: int = 401
    illegal_version: int = 426
