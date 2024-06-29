from ..version import Version


MAX_SIZE_SOFT: int = 64 * (2**20)
MAX_SIZE_HARD: int = 2 * MAX_SIZE_SOFT + 0x100
MIN_VERSION = Version("6.3.0")
PIPE_MAX_BYTES: int = 2**30
