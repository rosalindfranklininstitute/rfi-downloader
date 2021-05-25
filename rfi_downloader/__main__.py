from __future__ import annotations

import logging
import sys

import bugsnag
from bugsnag.handlers import BugsnagHandler
from .version import __version__

BUGSNAG_API_KEY = "d84798371c4ece309faa3c65598a8202"

logger = logging.getLogger(__name__)

bugsnag.configure(
    api_key=BUGSNAG_API_KEY,
    app_version=__version__,
    auto_notify=True,
    auto_capture_sessions=True,
    notify_release_stages=["production"],
)

# main entrypoint
def main():
    from .application import Application

    # set up logging
    monitor_logger = logging.getLogger("rfi_downloader")
    monitor_logger.setLevel(logging.DEBUG)

    log_fmt_long = logging.Formatter(
        fmt="%(asctime)s %(name)s %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # log to stdout
    log_handler_stream = logging.StreamHandler(sys.stdout)
    log_handler_stream.setFormatter(log_fmt_long)
    log_handler_stream.setLevel(logging.DEBUG)
    monitor_logger.addHandler(log_handler_stream)

    # log to bugsnag
    log_handler_bugsnag = BugsnagHandler()
    log_handler_bugsnag.setLevel(logging.WARNING)
    monitor_logger.addHandler(log_handler_bugsnag)

    app = Application()
    rv = app.run(sys.argv)
    sys.exit(rv)


if __name__ == "__main__":
    # execute only if run as the entry point into the program
    main()
