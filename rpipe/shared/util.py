from logging import WARNING, INFO, DEBUG, getLevelName, basicConfig, getLogger


_LOG_VERBOSITY: dict[int, int] = {0: WARNING, 1: INFO, 2: DEBUG}


def config_log(verbosity: int) -> None:
    lvl = _LOG_VERBOSITY[max(i for i in _LOG_VERBOSITY if i <= verbosity)]
    fmt = "%(asctime)s.%(msecs)03d - %(levelname)-8s - %(name)-10s - %(message)s"
    basicConfig(level=lvl, datefmt="%H:%M:%S", format=fmt)
    getLogger("shared").info("Logging level set to %s", getLevelName(lvl))
