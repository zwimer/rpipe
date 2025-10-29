from typing import TYPE_CHECKING, NamedTuple
from logging import getLogger
import hashlib

from Cryptodome.Random import get_random_bytes
from Cryptodome.Cipher import AES

from ...shared import TRACE, LFS

if TYPE_CHECKING:
    from collections.abc import Callable


class _EncryptedData(NamedTuple):
    text: bytes
    salt: bytes
    nonce: bytes
    tag: bytes

    def encode(self) -> bytes:
        line1 = b" ".join(str(len(i)).encode() for i in self) + b"\n"  # pylint: disable=not-an-iterable
        return line1 + b"".join(self)

    @classmethod
    def decode(cls, raw: bytes) -> list[_EncryptedData]:  # typing.Self in python3.11
        ret: list[_EncryptedData] = []  # python3.11 typing.Self
        end: int = 0
        while end < len(raw):  # We use this loop to avoid constantly slicing big data
            parts: list[bytes] = []
            start = raw.index(b"\n", end) + 1
            for i in (int(k.decode()) for k in raw[end : start - 1].split(b" ")):
                end = start + i
                parts.append(raw[start:end])
                start += i
            if len(parts) != len(cls._fields):
                raise ValueError("Bad encrypted data")
            ret.append(cls(*parts))
        return ret


def _aes(salt: bytes, password: str, nonce: bytes | None = None):
    scrypt = hashlib.scrypt(salt=salt, password=password.encode(), n=2**14, r=8, p=1, dklen=32)
    return AES.new(scrypt, AES.MODE_GCM, nonce=nonce)


def encrypt(data: bytes, compress: Callable[[bytes], bytes], password: str | None) -> bytes:
    log = getLogger("encrypt")
    if not password or not data:
        log.log(TRACE, "Not encrypting")
        return data
    log.debug("Compressing %s chunk", LFS(data))
    data = compress(data)
    log.debug("Encrypting compressed %s chunk", LFS(data))
    salt = get_random_bytes(AES.block_size)
    aes = _aes(salt, password)
    text, tag = aes.encrypt_and_digest(data)
    return _EncryptedData(text, salt, aes.nonce, tag).encode()


def decrypt(data: bytes, decompress: Callable[[bytes], bytes], password: str | None) -> bytes:
    log = getLogger("decrypt")
    if not password or not data:
        log.log(TRACE, "Not decrypting")
        return data
    log.debug("Extracting chunks from %s of data", LFS(data))
    es = _EncryptedData.decode(data)
    sfx = "s" if len(es) != 1 else ""
    log.debug("Decrypting %d chunk%s", len(es), sfx)
    r = [_aes(e.salt, password, e.nonce).decrypt_and_verify(e.text, e.tag) for e in es]
    log.debug("Decompressing %d chunk%s", len(es), sfx)
    r = [decompress(i) for i in r]
    if len(es) > 1:
        log.debug("Merging chunks")
    return r[0] if len(r) == 1 else b"".join(r)
