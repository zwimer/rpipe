class ReadCode:
    wrong_version: int = 412
    illegal_version: int = 409
    no_data: int = 410
    ok: int = 200


class WriteCode:
    missing_version: int = 412
    illegal_version: int = 409
    ok: int = 201


class Headers:  # Underscores are not allowed
    version_override: str = "Version-Override"
    client_version: str = "Client-Version"
