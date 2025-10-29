from dataclasses import dataclass, asdict
from typing import TYPE_CHECKING, TypeVar
from datetime import datetime
from json import dumps

from .version_ import Version, WEB_VERSION

if TYPE_CHECKING:
    from requests.structures import CaseInsensitiveDict
    from werkzeug.datastructures import MultiDict


# Servers may not have a MAX_SOFT_SIZE less than this
MAX_SOFT_SIZE_MIN: int = 8 * (1000**2)


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
# Other
#


# pylint: disable=too-many-instance-attributes
@dataclass(kw_only=True, frozen=True)
class QueryResponse:
    new: bool
    upload_complete: bool
    packets: int
    size: int
    encrypted: bool
    version: Version
    expiration: datetime
    locked: bool


@dataclass(kw_only=True, frozen=True)
class AdminMessage:
    body: str
    path: str
    uid: str

    def bytes(self) -> bytes:
        return dumps(asdict(self)).encode()
