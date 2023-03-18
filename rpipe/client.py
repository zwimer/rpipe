from typing import Optional
from pathlib import Path
import argparse
import json
import sys
import os

from marshmallow_dataclass import dataclass
import requests


config_file = Path.home() / ".config" / "pipe.json"


@dataclass
class Config:
    """
    Information about where the remote pipe is
    """
    url: str
    channel: str


#
# Actions
#


def _recv(config: Config, peek: bool):
    """
    Receive data from the remote pipe
    """
    r = requests.get(f"{config.url}/{'peek' if peek else 'read'}/{config.channel}")
    if not r.ok:
        raise RuntimeError(f"{r.status_code}: {r.text}")
    sys.stdout.buffer.write(r.content)
    sys.stdout.flush()

def _send(config: Config):
    """
    Send data to the remote pipe
    """
    data = sys.stdin.buffer.read()
    r = requests.post(f"{config.url}/write/{config.channel}", data=data)
    if not r.ok:
        raise RuntimeError(f"{r.status_code}: {r.text}")

def _clear(config: Config):
    """
    Clear the remote pipe
    """
    r = requests.get(f"{config.url}/clear/{config.channel}")
    if not r.ok:
        raise RuntimeError(f"{r.status_code}: {r.text}")


#
# Main
#


def pipe(print_config: bool, save_config: bool, url: Optional[str], channel: Optional[str], peek: bool, clear: bool):
    # Error checking
    if clear and peek:
        raise RuntimeError("--peek may not be used with --clear")
    has_stdin: bool = not os.isatty(sys.stdin.fileno())
    if has_stdin:
        if clear:
            raise RuntimeError("--clear may not be used when writing data to the pipe")
        if peek:
            raise RuntimeError("--peek may not be used when writing data to the pipe")
    # Configure if requested
    if save_config:
        if url is None or channel is None:
            raise RuntimeError("--url and --channel must be provided when using --save_config")
        if not config_file.parent.exists():
            config_file.parent.mkdir(exists_ok=True)
        out: str = Config.Schema().dumps(Config(url=url, channel=channel))
        with config_file.open("w") as f:
            f.write(out)
    # Load config, print if requested
    if print_config or url is None or channel is None:
        if not config_file.exists():
            raise RuntimeError("No config file found; please create one with --save_config.")
        try:
            with config_file.open("r") as f:
                conf: Config = Config.Schema().loads(f.read())
        except Exception as e:
            raise RuntimeError(f"Invalid config; please fix or remove {config_file}") from e
        if print_config:
            print(f"Saved Config: {conf}")
            return
        url = conf.url if url is None else url
        channel = conf.channel if channel is None else channel
    # Exec
    conf = Config(url=url, channel=channel)
    if clear:
        _clear(conf)
    elif has_stdin:
        _send(conf)
    else:
        _recv(conf, peek)


def _main(prog, *args):
    parser = argparse.ArgumentParser(prog=os.path.basename(prog))
    parser.add_argument("--print_config", action="store_true", help="Print out the saved config information then exit")
    parser.add_argument("-s", "--save_config", action="store_true", help=f"Configure {prog} to use the provided url and channel by default")
    parser.add_argument("-u", "--url", default=None, help="The pipe url to use")
    parser.add_argument("-c", "--channel", default=None, help="The channel to use")
    parser.add_argument("-p", "--peek", action="store_true", help="Read in 'peek' mode")
    parser.add_argument("--clear", action="store_true", help="Delete all entries in the channel")
    pipe(**vars(parser.parse_args(args)))


def main():
    _main(*sys.argv)

if __name__ == "__main__":
    main()
