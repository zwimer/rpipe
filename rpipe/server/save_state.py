from logging import getLogger, DEBUG
from datetime import datetime
from shutil import rmtree
from pathlib import Path
import pickle

from .globals import lock, streams, shutdown


_log = getLogger("save_state")

_TIMESTAMP: str = "TOD.bin"
_STREAM: str = "streams.bin"


def load(dir_: Path):
    """
    Load a saved program state
    """
    if len(streams):
        raise RuntimeError("Do not load a state on top of an existing state")
    print("Loading saved program state...")
    with lock:
        sf = dir_ / _STREAM
        if not sf.exists():
            return
        with sf.open("rb") as f:
            load_me = pickle.load(f)
        for i, k in load_me.items():
            streams[i] = k
        # Extend TTLs by the amount of time since the last save
        with (dir_ / _TIMESTAMP).open("rb") as f:
            offset = datetime.now() - pickle.load(f)
            print(f"Extending saved TTLs by {offset} to account for server downtime...")
            for i in streams.values():
                i.expire += offset
                print(i)


def save(dir_: Path):
    """
    Save the program state
    Do not call this unless the server is shutdown!
    """
    # TODO: save TOD
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
        with (dir_ / _TIMESTAMP).open("wb") as f:  # Save timestamp so we can extend TTLs on load
            pickle.dump(datetime.now(), f)
        print(streams)
        with (dir_ / _STREAM).open("wb") as f:
            pickle.dump(streams, f)
        if _log.isEnabledFor(DEBUG):
            _log.debug("Saved: %s", ", ".join(streams))
