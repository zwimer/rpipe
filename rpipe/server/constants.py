from ..version import Version


MAX_SIZE_SOFT: int = 128 * (2**20)
MAX_SIZE_HARD: int = 2 * MAX_SIZE_SOFT
MIN_VERSION = Version("5.1.0")
PIPE_MAX_BYTES = 2**30
