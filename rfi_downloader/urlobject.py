from __future__ import annotations

import gi

gi.require_version("Soup", "2.4")
from gi.repository import GObject, Soup, Gio, GLib
from humanfriendly import format_timespan

import logging
import time
from threading import RLock

from .utils import Session

logger = logging.getLogger(__name__)

# use a global session object
session = Session()

# read in blocks of 1MB
block_size = 1024 * 1024

# the minimum amount of time between successive progress property updates
progress_notify_delta = 1  # seconds


class URLObject(GObject.Object):

    __gproperties__ = {
        "progress": (
            float,  # type
            "progress",  # nick
            "progress",  # blurb
            0,  # min
            1,  # max
            1,  # default
            GObject.ParamFlags.READWRITE,  # flags
        ),
        "url": (
            str,  # type
            "url",  # nick
            "url",  # blurb
            None,
            GObject.ParamFlags.READABLE,  # flags
        ),
        "filename": (
            str,  # type
            "filename",  # nick
            "filename",  # blurb
            None,
            GObject.ParamFlags.READABLE,  # flags
        ),
        "relative-path": (
            str,  # type
            "relative-path",  # nick
            "relative-path",  # blurb
            None,
            GObject.ParamFlags.READABLE,  # flags
        ),
        "running": (
            bool,
            "running",
            "running",
            False,
            GObject.ParamFlags.READABLE,  # flags
        ),
        "paused": (
            bool,
            "paused",
            "paused",
            False,
            GObject.ParamFlags.READABLE,  # flags
        ),
        "finished": (
            bool,
            "finished",
            "finished",
            False,
            GObject.ParamFlags.READABLE,  # flags
        ),
    }

    def __init__(self, url: str, filename: str, relative_path: str):
        GObject.Object.__init__(self)
        self._progress: float = 0.0
        self._url: str = url
        self._filename: str = filename
        self._relative_path: str = relative_path
        self._running: bool = False
        self._paused: bool = False
        self._finished: bool = False
        self._error_message: str = None
        self._status_message: str = None
        self._should_pause: bool = False

        self._inputstream: Gio.InputStream = None
        self._outputstream: Gio.FileOutputStream = None
        self._cancellable = Gio.Cancellable()
        self._pause_main_loop: GLib.MainLoop = None
        self._pause_lock = RLock()

    def do_get_property(self, prop):
        py_prop_name: str = "_" + prop.name.replace("-", "_")
        if hasattr(self, py_prop_name):
            return getattr(self, py_prop_name)
        else:
            raise AttributeError("unknown property %s" % prop.name)

    def do_set_property(self, prop, value):
        py_prop_name: str = "_" + prop.name.replace("-", "_")
        if hasattr(self, py_prop_name):
            setattr(self, py_prop_name, value)
        else:
            raise AttributeError("unknown property %s" % prop.name)

    def get_error_message(self) -> str:
        return self._error_message

    def get_status_message(self) -> str:
        return self._status_message

    def start(self):
        logger.debug(f"Starting {self._url}")

        with self._pause_lock:
            if self._paused:
                logger.debug("Resuming download")
                self._pause_main_loop.quit()
                self._pause_main_loop = None
                self._paused = False
                self.notify("paused")
                return

        self._message = Soup.Message(method="GET", uri=Soup.URI.new(self._url))
        session.send_async(
            msg=self._message,
            cancellable=self._cancellable,
            callback=self._send_async_cb,
        )
        self._running = True
        self.notify("running")

    def _abort(self):
        if self._inputstream:
            self._inputstream.close_async(
                io_priority=GLib.PRIORITY_DEFAULT,
                cancellable=None,
                callback=self._input_stream_close_async_cb,
            )
        if self._outputstream:
            self._outputstream.close_async(
                io_priority=GLib.PRIORITY_DEFAULT,
                cancellable=None,
                callback=self._output_stream_close_async_cb,
            )
        else:
            self._running = False
            self.notify("running")
            self._finished = True
            self.notify("finished")

    def _input_stream_close_async_cb(
        self, inputstream: Gio.InputStream, result: Gio.AsyncResult, *user_data
    ):
        try:
            inputstream.close_finish(result)
        except GLib.Error as e:
            logger.warning(f"Error closing inputstream {e.message}")
        # No need to make a fuss if this fails. It shouldn't though.

    def _output_stream_close_async_cb(
        self, outputstream: Gio.FileOutputStream, result: Gio.AsyncResult, *user_data
    ):
        try:
            outputstream.close_finish(result)
        except GLib.Error as e:
            logger.warning(f"Error closing outputstream {e.message}")
            if self._error_message:
                logger.warning(f"Previous error message: {self._error_message}")
            self._error_message = e.message

        self._running = False
        self.notify("running")
        self._finished = True
        self.notify("finished")

    def _send_async_cb(
        self, session: Soup.Session, result: Gio.AsyncResult, *user_data
    ):
        try:
            self._inputstream = session.send_finish(result)
        except GLib.Error as e:
            self._error_message = e.message
            self._abort()
            return

        # confirm that we didnt run into an HTTP error code
        if (
            self._message.props.status_code < 200
            or self._message.props.status_code >= 300
        ):
            self._error_message = self._message.props.reason_phrase
            self._abort()
            return

        self._filesize = self._message.props.response_headers.get_content_length()
        logger.debug(f"File size: {self._filesize} for {self._filename}")

        # Open the file for writing
        self._last_progress_update = time.time()
        self._total_bytes_written = 0
        self._total_bytes_written_progress = (
            0  # used only for updating the progressbars
        )
        gfile: Gio.File = Gio.File.new_for_path(self._filename)

        # create the parent directories if necessary
        parent: Gio.File = gfile.get_parent()
        try:
            if parent:
                # there is no async variant of this method, otherwise I would have used it!
                parent.make_directory_with_parents(cancellable=self._cancellable)
        except GLib.Error as e:
            if e.code != Gio.IOErrorEnum.EXISTS:
                self._error_message = e.message
                self._abort()
                return

        gfile.replace_async(
            etag=None,
            make_backup=False,
            flags=Gio.FileCreateFlags.REPLACE_DESTINATION,
            io_priority=GLib.PRIORITY_DEFAULT,
            cancellable=self._cancellable,
            callback=self._replace_async_cb,
        )

    def _replace_async_cb(self, gfile: Gio.File, result: Gio.AsyncResult, *user_data):
        try:
            self._outputstream = gfile.replace_finish(result)
        except GLib.Error as e:
            self._error_message = e.message
            self._abort()
            return

        # The file is now open for writing -> start copying data from the inputstream
        self._inputstream.read_bytes_async(
            count=block_size,
            io_priority=GLib.PRIORITY_DEFAULT,
            cancellable=self._cancellable,
            callback=self._read_bytes_async_cb,
        )

    def _read_bytes_async_cb(
        self, inputstream: Gio.InputStream, result: Gio.AsyncResult, *user_data
    ):
        with self._pause_lock:
            if self._should_pause:
                self._pause_main_loop = GLib.MainLoop.new(None, False)
                self._should_pause = False
                self._paused = True
                self.notify("paused")

        # this has to be done outside the mutex as it will start a blocking loop
        if self._pause_main_loop:
            self._pause_main_loop.run()

        try:
            gbytes: GLib.Bytes = inputstream.read_bytes_finish(result)
        except GLib.Error as e:
            self._error_message = e.message
            self._abort()
            return

        if gbytes.get_size() == 0:
            # EOF -> download complete
            logger.info(f"No bytes returned for {self._filename}")
            self._progress = 1.0
            filesize_str = GLib.format_size(self._filesize)
            self._status_message = f"{filesize_str} of {filesize_str}"
            self.notify("progress")
            self._abort()
            return
        else:
            # write bytes to file
            self._outputstream.write_bytes_async(
                bytes=gbytes,
                io_priority=GLib.PRIORITY_DEFAULT,
                cancellable=self._cancellable,
                callback=self._write_bytes_async_cb,
            )

    def _write_bytes_async_cb(
        self, outputstream: Gio.OutputStream, result: Gio.AsyncResult, *user_data
    ):
        try:
            bytes_written = outputstream.write_bytes_finish(result)
        except GLib.Error as e:
            self._error_message = e.message
            self._abort()
            return

        self._total_bytes_written += bytes_written

        now = time.time()
        current_delta = now - self._last_progress_update

        if (current_delta > progress_notify_delta) and self._filesize > 0:
            self._progress = self._total_bytes_written / self._filesize
            speed = (
                self._total_bytes_written - self._total_bytes_written_progress
            ) / current_delta  # bytes/sec
            self._total_bytes_written_progress = self._total_bytes_written
            remaining_bytes = self._filesize - self._total_bytes_written
            remaining_time = remaining_bytes / speed  # sec
            self._status_message = (
                f"{GLib.format_size_full(self._total_bytes_written, GLib.FormatSizeFlags.LONG_FORMAT)}"
                + f" of {GLib.format_size(self._filesize)}"
                + f" ({self._progress:.1%}, {GLib.format_size(speed)}/sec),"
                + f" {format_timespan(remaining_time)} remaining"
            )
            self._last_progress_update = now
            self.notify("progress")

        # read some more bytes
        self._inputstream.read_bytes_async(
            count=block_size,
            io_priority=GLib.PRIORITY_DEFAULT,
            cancellable=self._cancellable,
            callback=self._read_bytes_async_cb,
        )

    def stop(self):
        logger.debug(f"Calling stop")
        if self._finished:
            return
        with self._pause_lock:
            if self._paused:
                self._pause_main_loop.quit()
                self._paused = (
                    False  # no need to bother with notifications at this point
                )

        if self._running:
            logger.debug(f"Cancelling")
            self._cancellable.cancel()

    def pause(self):
        logger.debug(f"Calling pause")
        with self._pause_lock:
            if self._paused or self._should_pause or not self._running:
                return
            self._should_pause = True
