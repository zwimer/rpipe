from logging import DEBUG, INFO, StreamHandler, FileHandler, getLevelName, getLogger, shutdown
from os import environ, close as fd_close
from dataclasses import dataclass
from tempfile import mkstemp
from functools import wraps
from pathlib import Path
import atexit

from flask import Response, Flask, send_file, request
from zstdlib.log import CuteFormatter
import waitress

from ..shared import BLOCKED_EC, TRACE, restrict_umask, remote_addr, log, __version__
from .util import MAX_SIZE_HARD, MIN_VERSION, json_response, plaintext
from .channel import handler, query
from .blocked import Blocked
from .server import Server
from .admin import Admin


_LOG = "app"


@dataclass(frozen=True, slots=True, kw_only=True)
class LogConfig:
    colored: bool
    log_file: Path
    verbose: int
    debug: bool


@dataclass(frozen=True, slots=True, kw_only=True)
class ServerConfig:
    host: str
    port: int
    debug: bool
    state_file: Path | None
    blocklist: Path | None
    key_files: list[Path]


class App(Flask):

    @dataclass(frozen=True, slots=True)
    class Objs:
        admin: Admin
        server: Server
        blocked: Blocked
        favicon: Path | None

    def __init__(self) -> None:
        super().__init__(f"rpipe_server {__version__}")
        getLogger(_LOG).info("Setting max packet size: %s", log.LFS(MAX_SIZE_HARD))
        self.config["MAX_CONTENT_LENGTH"] = MAX_SIZE_HARD
        self.url_map.strict_slashes = False

    def start(self, conf: ServerConfig, log_file: Path, favicon: Path | None):
        lg = getLogger(_LOG)
        if favicon is not None and not favicon.is_file():
            lg.error("Favicon file not found: %s", favicon)
            favicon = None
        blocked = Blocked(conf.blocklist, conf.debug)
        admin = Admin(log_file, conf.key_files, blocked)
        lg.info("Starting server version: %s", __version__)
        # pylint: disable=attribute-defined-outside-init
        self._objs = self.Objs(admin, Server(conf.debug, conf.state_file), blocked, favicon)
        lg.info("Binding to %s:%s", conf.host, conf.port)
        if conf.debug:
            self.run(host=conf.host, port=conf.port, debug=True)
        else:
            waitress.serve(self, host=conf.host, port=conf.port, clear_untrusted_proxy_headers=False)

    def give(self, *, objs: bool = False, logged: bool = True):
        """
        Give the wrapped function self.objs and log requests as requested
        Also handles blocked IP addresses and routes
        """
        lg = getLogger(_LOG)

        def decorator(func):
            @wraps(func)
            def inner(*args, **kwargs):
                if self._objs.blocked():
                    if lg.isEnabledFor(DEBUG):
                        lg.debug("Blocked request by %s to: %s", remote_addr(), request.path)
                    return Response(status=BLOCKED_EC)
                ret = func(*args, self._objs, **kwargs) if objs else func(*args, **kwargs)
                if not logged or self._objs.server.state.debug:
                    return ret
                # Release mode: Log the request before returning it, Flask in debug mode does automatically
                quiet = ret.status_code == 404 and request.full_path.strip("?") == "/favicon.ico"
                lvl = DEBUG if (quiet or ret.status_code in (410, 425) or ret.status_code < 300) else INFO
                lvl = TRACE if request.method in ("OPTIONS", "HEAD") else lvl
                args = (remote_addr(), request.method, request.full_path.strip("?"), ret.status_code)
                lg.log(lvl, '%s - "%s %s" %d', *args)
                return ret

            return inner

        return decorator

    def route(self, *paths, admin: bool = False, objs: bool = False, logged: bool = True, **kwargs):
        """
        Route decorator that allows for multiple paths to be routed to the same function
        Automatically applies the give decorator with objs=objs and logged=logged
        If admin, set objs=True and set methods=["POST"] if not set
        """
        if not paths:
            raise ValueError("At least one path is required")
        if admin and "methods" not in kwargs:
            kwargs["methods"] = ["POST"]
        super_route = super().route

        def wrapper(func):
            ret = self.give(objs=admin or objs, logged=logged)(func)
            for p in paths:
                ret = super_route(p, **kwargs)(ret)
            return ret

        return wrapper


app = App()


#
# Routes
#


@app.errorhandler(404)
@app.give()
def _page_not_found(_, *, quiet=False) -> Response:
    lg = getLogger(_LOG)
    if not quiet:
        lg.warning("404: Not found: %s", request.path)
    (lg.debug if quiet else lg.info)("Headers: %s", request.headers)
    return Response("404: Not found", status=404)


@app.route("/", "/help")
def _help() -> Response:
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


@app.route("/favicon.ico", objs=True, logged=False)
def _favicon(o: App.Objs) -> Response:
    return _page_not_found(404, quiet=True) if o.favicon is None else send_file(o.favicon)


@app.route("/robots.txt")
def _robots_txt() -> Response:
    return plaintext("User-agent: *\nDisallow: /\nAllow: /help")


@app.route("/version")
def _show_version() -> Response:
    return plaintext(__version__)


@app.route("/supported")
def _supported() -> Response:
    return json_response({"min": str(MIN_VERSION), "banned": []})


@app.route("/c/<channel>", objs=True, methods=["DELETE", "GET", "POST", "PUT"])
def _channel(o: App.Objs, channel: str) -> Response:
    return handler(o.server.state, channel)


@app.route("/q/<channel>", objs=True)
def _query(o: App.Objs, channel: str) -> Response:
    return query(o.server.state, channel)


# Admin routes


@app.route("/admin/uid", admin=True, methods=["GET"])
def _admin_uid(o: App.Objs) -> Response:
    """
    Get a few UIDSs needed to sign admin requests
    The exact number is up to the server, if you need more, request more
    These UIDs will expire after a short period of time
    """
    return o.admin.uids()


@app.route("/admin/debug", admin=True)
def _admin_debug(o: App.Objs) -> Response:
    return o.admin.debug(o.server.state)


@app.route("/admin/channels", admin=True)
def _admin_channels(o: App.Objs) -> Response:
    return o.admin.channels(o.server.state)


@app.route("/admin/stats", admin=True)
def _admin_stats(o: App.Objs) -> Response:
    with o.blocked as data:
        return o.admin.stats(o.server.state, data.stats)


@app.route("/admin/log", admin=True)
def _admin_log(o: App.Objs) -> Response:
    return o.admin.log(o.server.state)


@app.route("/admin/log-level", admin=True)
def _admin_log_level(o: App.Objs) -> Response:
    return o.admin.log_level(o.server.state)


@app.route("/admin/lock", admin=True)
def _admin_lock(o: App.Objs) -> Response:
    return o.admin.lock(o.server.state)


@app.route("/admin/ip", admin=True)
def _admin_ip(o: App.Objs) -> Response:
    return o.admin.ip(o.server.state)


@app.route("/admin/route", admin=True)
def _admin_route(o: App.Objs) -> Response:
    return o.admin.route(o.server.state)


# Main functions


def _log_shutdown(log_file: Path) -> None:
    getLogger().critical("Logger is shutting down. Purging: %s", log_file)
    shutdown()
    # Missing is an error, but we ignore it since it's not critical and we are shutting down
    log_file.unlink(missing_ok=True)


def _log_config(conf: LogConfig) -> Path:
    rdlf_env: str = "_REUSE_DEBUG_LOG_FILE"
    log.define_trace()
    log_file = conf.log_file
    # Flask debug mode may restart the server without cleaning up, we reuse the log file here
    if reuse_log_file := log_file is None and conf.debug and rdlf_env in environ:
        log_file = Path(environ[rdlf_env])
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
                environ[rdlf_env] = str(log_file)
    # Setup logger
    fmt = CuteFormatter(**log.CF_KWARGS, colored=conf.colored)  # type: ignore[arg-type]
    fh = FileHandler(log_file, mode="a")
    stream = StreamHandler()
    root = getLogger()
    for i in (fh, stream):
        i.setFormatter(fmt)
        root.addHandler(i)
    # Set level
    lvl: int = log.level(conf.verbose)
    root.setLevel(lvl)
    root.info(
        "Logging level set to %s with colors %sABLED", getLevelName(lvl), "EN" if conf.colored else "DIS"
    )
    if reuse_log_file:
        root.warning("Reusing debug log file: %s", log_file)
    # Cleanup and return the log file
    return log_file


def serve(conf: ServerConfig, log_conf: LogConfig, favicon: Path) -> None:
    app.start(conf, _log_config(log_conf), favicon)
