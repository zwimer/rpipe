from logging import getLogger, DEBUG
from shutil import rmtree
from pathlib import Path
import pickle

from .globals import lock, streams, shutdown


_log = getLogger("save_state")


def load(dir_: Path):
    """
    Load a saved program state
    """
    if len(streams):
        raise RuntimeError("Do not load a state on top of an existing state")
    print("Loading saved program state...")
    with lock:
        for p in dir_.iterdir():
            _log.debug("Loading channel %s", p.name)
            with p.open("rb") as f:
                streams[p.name] = pickle.load(f)  # nosec B301


def save(dir_: Path):
    """
    Save the program state
    Do not call this unless the server is shutdown!
    """
    if not shutdown:
        raise RuntimeError("Do save state before shutdown")
    _log.debug("Purging old program state...")
    if dir_.exists():
        rmtree(dir_)
    dir_.mkdir()
    with lock:
        print("Saving program state...")
        if not streams:
            return
        for name, data in streams.items():
            with (dir_ / name).open("wb") as f:
                pickle.dump(data, f)
        if _log.isEnabledFor(DEBUG):
            _log.debug("Saved: %s", ", ".join(streams))
