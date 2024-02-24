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


def _aes(salt: bytes, password: str, nonce: bytes | None = None):
    scrypt = hashlib.scrypt(salt=salt, password=password.encode(), n=2**14, r=8, p=1, dklen=32)
    return AES.new(scrypt, AES.MODE_GCM, nonce=nonce)


def encrypt(data: bytes, password: str | None) -> bytes:
    if not password or not data:
        return data
    salt = get_random_bytes(AES.block_size)
    aes = _aes(salt, password)
    text, tag = aes.encrypt_and_digest(zlib.compress(data, level=_ZLIB_LEVEL))
    return _EncryptedData(text, salt, aes.nonce, tag).encode()


def decrypt(data: bytes, password: str | None) -> bytes:
    if not password or not data:
        return data
    e = _EncryptedData.decode(data)
    aes = _aes(e.salt, password, e.nonce)
    return zlib.decompress(aes.decrypt_and_verify(e.text, e.tag))
