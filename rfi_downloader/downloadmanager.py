from __future__ import annotations

from gi.repository import GObject, GLib

from .utils.exceptions import AlreadyRunning, NotYetRunning

import logging
from threading import RLock

logger = logging.getLogger(__name__)


class DownloadManager(GObject.Object):
    def __init__(self, appwindow):
        GObject.Object.__init__(self)

        self._model_lock = RLock()
        self._appwindow = appwindow
        self._running: bool = False
        self._paused: bool = False
        self._finished: bool = False
        self._max_active_urls: int = 1  # this could become a configurable parameter
        self._active_urls: int = 0

    @GObject.Property(type=bool, default=False)
    def running(self):
        return self._running

    @GObject.Property(type=bool, default=False)
    def paused(self):
        return self._paused

    @GObject.Property(type=bool, default=False)
    def finished(self):
        return self._finished

    def start(self):
        # start
        if self._running:
            raise AlreadyRunning(
                "The download manager is already running. It needs to be stopped before it may be restarted"
            )

        if self._paused:
            self._paused = False
            self.notify("paused")
            return

        # hook up to each of the urls' finished signal
        for url in self._appwindow._model:
            url.connect("notify::finished", self._url_finished_cb)

        self._running = True
        self._timeout_id = GLib.timeout_add_seconds(
            1, self._model_timeout_cb, priority=GLib.PRIORITY_DEFAULT
        )
        self.notify("running")

    def pause(self):
        pass

    def stop(self):
        # remove timeout
        if not self._running:
            raise NotYetRunning(
                "The download manager needs to be started before it can be stopped."
            )

        GLib.source_remove(self._timeout_id)
        with self._model_lock:
            for url in self._appwindow._model:
                if url.props.running:
                    url.stop()

        self._running = False
        self.notify("running")
        self._finished = True
        self.notify("finished")

    def _url_finished_cb(self, url, param):
        with self._model_lock:
            if url.props.finished:
                self._active_urls -= 1

    def _model_timeout_cb(self):
        with self._model_lock:
            number_of_finished_urls = 0
            for url in self._appwindow._model:
                if url.props.finished:
                    number_of_finished_urls += 1
                elif self._paused and not url.props.paused and url.props.running:
                    # pause if necessary
                    url.pause()
                elif not self._paused and self._active_urls < self._max_active_urls:
                    # resume or start
                    url.start()
                    self._active_urls += 1

            if number_of_finished_urls == len(self._appwindow._model):
                # all jobs have been finished
                self._running = False
                self.notify("running")
                self._finished = True
                self.notify("finished")
                return GLib.SOURCE_REMOVE

        # keep the timeout going
        return GLib.SOURCE_CONTINUE
