from typing import NamedTuple, Dict, Optional
from datetime import datetime, timedelta
from threading import Thread, RLock
import argparse
import time
import sys
import os

from flask import Flask, Response, request, redirect
import waitress

#
# Types
#

class Data(NamedTuple):
    """
    A timestamped bytes class
    """
    data: bytes
    when: datetime

#
# Globals
#

data: Dict[str, Data] = {}
lock = RLock()

app = Flask(__name__)
app.url_map.strict_slashes = False

#
# Helpers
#

def _get(channel: str, delete: bool):
    with lock:
        got: Optional[Data] = data.get(channel, None)
        if delete and got is not None:
            del data[channel]
    if got is None:
        return f"No data on channel {channel}", 400
    return got.data


def _periodic_prune():
    prune_age = timedelta(minutes=5)
    while True:
        old: datetime = datetime.now() - prune_age
        with lock:
            for i in [i for i,k in data.items() if k.when < old]:
                del data[i]
        time.sleep(60)

#
# Routes
#

@app.route("/help")
def _help():
    return "Write to /write, read from /read or /peek, clear with /clear; add a trailing /<channel> to specify the channel"


@app.route("/")
def _root():
    return _help()


@app.route("/clear/<channel>")
def _clear(channel: str):
    with lock:
        if channel in data:
            del data[channel]
    return Response(status=204)


@app.route("/peek/<channel>")
def _peek(channel: str):
    return _get(channel, False)


@app.route("/read/<channel>")
def _read(channel: str):
    return _get(channel, True)


@app.route("/write/<channel>", methods=["POST"])
def _write(channel: str):
    with lock:
        data[channel] = Data(request.get_data(), datetime.now())
    return Response(status=204)

#
# Main
#

def start(host: str, port: int):
    Thread(target=_periodic_prune, daemon=True).start()
    # app.run(debug=True)
    waitress.serve(app, host="0.0.0.0", port=8081)


def _main(prog, *args):
    parser = argparse.ArgumentParser(prog=os.path.basename(prog))
    parser.add_argument("--host", default="0.0.0.0", help="The host waitress will bind to for listening")
    parser.add_argument("port", type=int, help="The port waitress will listen on")
    start(**vars(parser.parse_args(args)))


def main():
    _main(*sys.argv)

if __name__ == "__main__":
    main()
