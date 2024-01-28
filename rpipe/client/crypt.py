import hashlib
import zlib

from Cryptodome.Random import get_random_bytes
from Cryptodome.Cipher import AES


_ZLIB_LEVEL: int = 6


def _merge(*args: bytes) -> bytes:
    line1 = b" ".join(str(len(i)).encode() for i in args) + b"\n"
    return b"".join([line1, *args])


def _split(raw: bytes) -> list[bytes]:
    ret = []
    start = raw.index(b"\n") + 1
    for i in (int(k.decode()) for k in raw[: start - 1].split(b" ")):
        ret.append(raw[start : start + i])
        start += i
    return ret


def _opts(password: str) -> dict:
    return {"password": password.encode(), "n": 2**14, "r": 8, "p": 1, "dklen": 32}


def encrypt(data: bytes, password: str | None) -> bytes:
    if not password or not data:
        return data
    salt = get_random_bytes(AES.block_size)
    conf = AES.new(hashlib.scrypt(salt=salt, **_opts(password)), AES.MODE_GCM)  # type: ignore
    text, tag = conf.encrypt_and_digest(zlib.compress(data, level=_ZLIB_LEVEL))
    return _merge(text, salt, conf.nonce, tag)


def decrypt(data: bytes, password: str | None) -> bytes:
    if not password or not data:
        return data
    text, salt, nonce, tag = _split(data)
    aes = AES.new(hashlib.scrypt(salt=salt, **_opts(password)), AES.MODE_GCM, nonce=nonce)  # type: ignore
    return zlib.decompress(aes.decrypt_and_verify(text, tag))
