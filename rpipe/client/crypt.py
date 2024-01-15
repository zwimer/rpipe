from base64 import b64encode, b64decode
import hashlib
import zlib

from Cryptodome.Random import get_random_bytes
from Cryptodome.Cipher import AES


_ZLIB_LEVEL: int = 6


def _opts(password: str) -> dict:
    return {"password": password.encode(), "n": 2**14, "r": 8, "p": 1, "dklen": 32}


def encrypt(data: bytes, password: str | None) -> bytes:
    if password is None or not data:
        return data
    salt = get_random_bytes(AES.block_size)
    conf = AES.new(hashlib.scrypt(salt=salt, **_opts(password)), AES.MODE_GCM)  # type: ignore
    text, tag = conf.encrypt_and_digest(zlib.compress(data, level=_ZLIB_LEVEL))
    return b".".join(b64encode(i) for i in (text, salt, conf.nonce, tag))


def decrypt(data: bytes, password: str | None) -> bytes:
    if password is None or not data:
        return data
    text, salt, nonce, tag = (b64decode(i) for i in data.split(b"."))
    aes = AES.new(hashlib.scrypt(salt=salt, **_opts(password)), AES.MODE_GCM, nonce=nonce)  # type: ignore
    return zlib.decompress(aes.decrypt_and_verify(text, tag))
