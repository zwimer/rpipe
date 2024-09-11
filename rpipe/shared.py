from __future__ import annotations
from logging import basicConfig, getLogger, getLevelName, WARNING, INFO, DEBUG
from dataclasses import dataclass, asdict, astuple, field
from typing import TYPE_CHECKING, TypeVar
from enum import Enum, unique

from .version import Version

if TYPE_CHECKING:
    from requests.structures import CaseInsensitiveDict
    from werkzeug.datastructures import MultiDict
    from datetime import datetime


WEB_VERSION = Version("0.0.0")
assert not WEB_VERSION.invalid()  # nosec B101
_LOG_VERBOSITY: dict[int, int] = {0: WARNING, 1: INFO, 2: DEBUG}


def config_log(verbosity: int) -> None:
    lvl = _LOG_VERBOSITY[max(i for i in _LOG_VERBOSITY if i <= verbosity)]
    fmt = "%(asctime)s.%(msecs)03d - %(levelname)-8s - %(name)-10s - %(message)s"
    basicConfig(level=lvl, datefmt="%H:%M:%S", format=fmt)
    getLogger("shared").info("Logging level set to %s", getLevelName(lvl))


@dataclass
class _ToDict:
    def to_dict(self) -> dict[str, str]:
        return {i.replace("_", "-"): str(k) for i, k in asdict(self).items() if k is not None}


def _get_bool(d: dict[str, str], name: str, default: bool) -> bool:
    return d.get(name, str(default)) == "True"


def _get_int_or_none(d: dict[str, str], name: str) -> int | None:
    got: str | None = d.get(name, None)
    if isinstance(got, str):
        try:
            return int(got)  # If we can't convert to an int, we'll just return None
        except ValueError:
            pass
    return None


#
# Error Codes
#


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


#
# Request Params
#


@dataclass(kw_only=True)
class UploadRequestParams(_ToDict):
    version: Version
    encrypted: bool
    final: bool = False
    override: bool = False
    stream_id: str | None = None  # Not required for initial upload POST
    ttl: int | None = None  # Use None if not provided (only read during initial upload POST)

    @classmethod
    def from_dict(cls, d: MultiDict[str, str]) -> UploadRequestParams:
        return cls(
            version=Version(d.get("version", WEB_VERSION.str)),
            encrypted=_get_bool(d, "encrypted", False),
            final=_get_bool(d, "final", False),
            override=_get_bool(d, "override", False),
            stream_id=d.get("stream-id", None),
            ttl=_get_int_or_none(d, "ttl"),
        )


@dataclass(kw_only=True)
class DownloadRequestParams(_ToDict):
    version: Version
    delete: bool
    override: bool = False
    stream_id: str | None = None  # Not required for initial upload GET

    @classmethod
    def from_dict(cls, d: MultiDict[str, str]) -> DownloadRequestParams:
        return cls(
            version=Version(d.get("version", WEB_VERSION.str)),
            delete=_get_bool(d, "delete", False),
            override=_get_bool(d, "override", False),
            stream_id=d.get("stream-id", None),
        )


#
# Response Headers
#


class BadHeaders(RuntimeError):
    """
    Raised a response's headers are bad
    """


_Self = TypeVar("_Self", bound="_ResponseHeaders")  # typing.Self in python3.11


class _ResponseHeaders(_ToDict):
    @classmethod
    def from_dict(cls: type[_Self], d: CaseInsensitiveDict[str]) -> _Self:
        try:
            return cls._from_dict(dict(d.lower_items()))
        except KeyError as e:
            raise BadHeaders("Missing headers") from e

    @classmethod
    def _from_dict(cls: type[_Self], d: dict[str, str]) -> _Self:
        raise NotImplementedError()


@dataclass(kw_only=True)
class UploadResponseHeaders(_ResponseHeaders):
    stream_id: str
    max_size: int

    @classmethod
    def _from_dict(cls, d: dict[str, str]) -> UploadResponseHeaders:
        return cls(stream_id=d["stream-id"], max_size=int(d["max-size"]))


@dataclass(kw_only=True)
class DownloadResponseHeaders(_ResponseHeaders):
    stream_id: str
    final: bool
    encrypted: bool

    @classmethod
    def _from_dict(cls, d: dict[str, str]) -> DownloadResponseHeaders:
        return cls(
            stream_id=d["stream-id"],
            final=d["final"] == "True",
            encrypted=d["encrypted"] == "True",
        )


#
# Admin types
#


@dataclass(kw_only=True, frozen=True)
class AdminMessage:
    args: dict[str, str] = field(default_factory=dict)
    path: str
    uid: str

    def bytes(self) -> bytes:
        return str(astuple(self)).encode()


@dataclass(kw_only=True, frozen=True)
class AdminPOST:
    signature: bytes
    version: str
    uid: str

    @classmethod
    def from_json(cls, d: dict[str, str]) -> AdminPOST:
        s = bytes.fromhex(d.pop("signature"))
        return cls(signature=s, **d)

    def json(self) -> dict[str, str]:
        ret = asdict(self)
        ret["signature"] = self.signature.hex()
        return ret


@dataclass(kw_only=True)
class ChannelInfo:
    version: Version
    packets: int
    size: int
    encrypted: bool
    expire: datetime
