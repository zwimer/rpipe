from dataclasses import dataclass, asdict


WEB_VERSION = "0.0.0"
ENCRYPTED_HEADER = "encrypted"


class ErrorCode:
    """
    HTTP error codes the rpipe client may be sent
    """

    wrong_version: int = 412
    illegal_version: int = 409
    no_data: int = 410


@dataclass(kw_only=True, frozen=True)
class RequestParams:
    version: str
    override: bool = False  # Not passed for upload
    encrypted: bool = False  # Not passed for download

    def to_dict(self) -> dict[str, str]:
        return {i: str(k) for i, k in asdict(self).items()}

    @classmethod
    def from_dict(cls, d: dict[str, str]) -> "RequestParams":
        return cls(
            version=d.get("version", WEB_VERSION),
            override=d.get("override", "") == "True",
            encrypted=d.get("encrypted", "") == "True",
        )
