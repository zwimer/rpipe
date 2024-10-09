from __future__ import annotations
from logging import StreamHandler, FileHandler, Formatter, getLevelName, getLogger, shutdown
from os import environ, close as fd_close
from dataclasses import dataclass
from tempfile import mkstemp
from pathlib import Path
import atexit

from flask import Response, Flask, request
import waitress

from ..shared import restrict_umask, log, __version__
from .util import MAX_SIZE_HARD, plaintext
from .channel import handler, query
from .server import Server
from .admin import Admin


app = Flask(f"rpipe_server {__version__}")
_REUSE_DEBUG_LOG_FILE = "_REUSE_DEBUG_LOG_FILE"
server = Server()
admin = Admin()
_LOG = "app"


#
# Dataclasses
#


@dataclass(frozen=True, kw_only=True)
class LogConfig:
    log_file: Path
    verbose: bool
    debug: bool


@dataclass(frozen=True, kw_only=True)
class ServerConfig:
    host: str
    port: int
    debug: bool
    state_file: Path | None
    key_files: list[Path]


#
# Routes
#


@app.errorhandler(404)
def page_not_found(_) -> Response:
    getLogger(_LOG).warning("404: Request for %s", request.full_path)
    return Response("404: Not found", status=404)


@app.route("/")
@app.route("/help")
def _help() -> Response:
    getLogger(_LOG).info("Request for /help")
    msg = (
        "Welcome to the web UI of rpipe. "
        "To interact with a given channel, use the path /c/<channel>. "
        "To read a message from a given channel, use a GET request. "
        "To write a message to a given channel, use PUT and POST requests. "
        "To delete a channel, use a DELETE request. "
        "Note: Using the web version bypasses version consistent checks "
        "and may result in safe but unexpected behavior (such as failing "
        "an uploaded message; if possible use the rpipe client CLI instead. "
        "Install the CLI via: pip install rpipe"
    )
    return plaintext(msg)


@app.route("/version")
def _show_version() -> Response:
    getLogger(_LOG).info("Request for /version")
    return plaintext(__version__)


@app.route("/c/<channel>", methods=["DELETE", "GET", "POST", "PUT"])
def _channel(channel: str) -> Response:
    return handler(server.state, channel)


@app.route("/q/<channel>")
def _query(channel: str) -> Response:
    return query(server.state, channel)


# Admin routes


@app.route("/admin/uid")
def _admin_uid() -> Response:
    """
    Get a few UIDSs needed to sign admin requests
    The exact number is up to the server, if you need more, request more
    These UIDs will expire after a short period of time
    """
    return admin.uids()


@app.route("/admin/debug", methods=["POST"])
def _admin_debug() -> Response:
    return admin.debug(server.state)


@app.route("/admin/channels", methods=["POST"])
def _admin_channels() -> Response:
    return admin.channels(server.state)


@app.route("/admin/stats", methods=["POST"])
def _admin_stats() -> Response:
    return admin.stats(server.state)


@app.route("/admin/log", methods=["POST"])
def _admin_log() -> Response:
    return admin.log(server.state)


@app.route("/admin/log-level", methods=["POST"])
def _admin_log_level() -> Response:
    return admin.log_level(server.state)


# Serve


def _log_shutdown(log_file: Path) -> None:
    getLogger().critical("Logger is shutting down. Purging: %s", log_file)
    shutdown()
    # Missing is an error, but we ignore it since it's not critical and we are shutting down
    log_file.unlink(missing_ok=True)


def _log_config(conf: LogConfig) -> Path:
    log.define_trace()
    log_file = conf.log_file
    # Flask debug mode may restart the server without cleaning up, we reuse the log file here
    if reuse_log_file := log_file is None and conf.debug and _REUSE_DEBUG_LOG_FILE in environ:
        log_file = Path(environ[_REUSE_DEBUG_LOG_FILE])
    # Determine which file to log to
    with restrict_umask(0o6):
        if log_file is not None:
            # We force creation to ensure proper permissions
            with log_file.open("a", encoding="utf8") as f:
                f.write("" if f.tell() == 0 else "\n")
        else:
            fd, fpath = mkstemp(suffix=".log")
            fd_close(fd)
            log_file = Path(fpath)
            atexit.register(_log_shutdown, log_file)
            if conf.debug:
                environ[_REUSE_DEBUG_LOG_FILE] = str(log_file)
    # Setup logger
    fmt = Formatter(log.FORMAT, log.DATEFMT)
    fh = FileHandler(log_file, mode="a")
    stream = StreamHandler()
    root = getLogger()
    for i in (fh, stream):
        i.setFormatter(fmt)
        root.addHandler(i)
    # Set level
    lvl: int = log.level(conf.verbose)
    root.setLevel(lvl)
    root.info("Logging level set to %s", getLevelName(lvl))
    if reuse_log_file:
        root.warning("Reusing debug log file: %s", log_file)
    # Cleanup and return
    return log_file


# pylint: disable=too-many-arguments
def serve(conf: ServerConfig, log_conf: LogConfig) -> None:
    log_file = _log_config(log_conf)
    lg = getLogger(_LOG)
    lg.info("Setting max packet size: %s", log.LFS(MAX_SIZE_HARD))
    app.config["MAX_CONTENT_LENGTH"] = MAX_SIZE_HARD
    app.url_map.strict_slashes = False
    admin.init(log_file, conf.key_files)
    lg.info("Starting server version: %s", __version__)
    server.start(conf.debug, conf.state_file)
    lg.info("Serving on %s:%s", conf.host, conf.port)
    if conf.debug:
        app.run(host=conf.host, port=conf.port, debug=True)
    else:
        waitress.serve(app, host=conf.host, port=conf.port)
