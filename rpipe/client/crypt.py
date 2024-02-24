from __future__ import annotations
from typing import NamedTuple
import hashlib
import zlib

from Cryptodome.Random import get_random_bytes
from Cryptodome.Cipher import AES


_ZLIB_LEVEL: int = 6


class _EncryptedData(NamedTuple):
    text: bytes
    salt: bytes
    nonce: bytes
    tag: bytes

    def encode(self) -> bytes:
        line1 = b" ".join(str(len(i)).encode() for i in self) + b"\n"  # pylint: disable=not-an-iterable
        return line1 + b"".join(self)

    @classmethod
    def decode(cls, raw: bytes) -> _EncryptedData:  # typing.Self in python3.11
        parts = []
        start = raw.index(b"\n") + 1
        for i in (int(k.decode()) for k in raw[: start - 1].split(b" ")):
            parts.append(raw[start : start + i])
            start += i
        if len(parts) != len(cls._fields):
            raise RuntimeError("Bad encrypted data")
        return cls(*parts)


def _opts(password: str) -> dict:
    return {"password": password.encode(), "n": 2**14, "r": 8, "p": 1, "dklen": 32}


def encrypt(data: bytes, password: str | None) -> bytes:
    if not password or not data:
        return data
    salt = get_random_bytes(AES.block_size)
    conf = AES.new(hashlib.scrypt(salt=salt, **_opts(password)), AES.MODE_GCM)  # type: ignore
    text, tag = conf.encrypt_and_digest(zlib.compress(data, level=_ZLIB_LEVEL))
    return _EncryptedData(text, salt, conf.nonce, tag).encode()


def decrypt(data: bytes, password: str | None) -> bytes:
    if not password or not data:
        return data
    e = _EncryptedData.decode(data)
    aes = AES.new(hashlib.scrypt(salt=e.salt, **_opts(password)), AES.MODE_GCM, nonce=e.nonce)  # type: ignore
    return zlib.decompress(aes.decrypt_and_verify(e.text, e.tag))
