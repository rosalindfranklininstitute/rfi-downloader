import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gtk, Gdk, Gio, GLib, Pango

from .urlobject import URLObject
from .utils import EXPAND_AND_FILL

import logging
import os

logger = logging.getLogger(__name__)


class URLListBoxRow(Gtk.ListBoxRow):
    def __init__(self, url_object: URLObject):
        super().__init__(
            hexpand=True,
            vexpand=False,
            halign=Gtk.Align.FILL,
            valign=Gtk.Align.CENTER,
            activatable=False,
        )

        frame = Gtk.Frame(
            **EXPAND_AND_FILL,
            margin_bottom=2,
            margin_top=2,
            margin_left=2,
            margin_right=2,
        )
        grid = Gtk.Grid(
            **EXPAND_AND_FILL,
            margin_bottom=2,
            margin_top=2,
            margin_left=2,
            margin_right=2,
        )
        frame.add(grid)
        self.add(frame)

        grid.attach(
            Gtk.Image(
                icon_name="emblem-downloads",
                icon_size=Gtk.IconSize.DIALOG,
                hexpand=False,
                vexpand=True,
                halign=Gtk.Align.START,
                valign=Gtk.Align.CENTER,
            ),
            0,
            0,
            1,
            3,
        )

        grid.attach(
            Gtk.Label(
                label=f"<b>{os.path.basename(url_object.props.filename)}</b>",
                use_markup=True,
                ellipsize=Pango.EllipsizeMode.END,
                halign=Gtk.Align.START,
                valign=Gtk.Align.CENTER,
                hexpand=True,
                vexpand=False,
            ),
            1,
            0,
            1,
            1,
        )

        self._progress_bar = Gtk.ProgressBar(
            halign=Gtk.Align.FILL,
            valign=Gtk.Align.CENTER,
            hexpand=True,
            vexpand=False,
        )
        grid.attach(self._progress_bar, 1, 1, 1, 1)

        self._status_label = Gtk.Label(
            label=f"Download not started",
            use_markup=True,
            ellipsize=Pango.EllipsizeMode.END,
            halign=Gtk.Align.START,
            valign=Gtk.Align.CENTER,
            hexpand=True,
            vexpand=False,
        )
        grid.attach(self._status_label, 1, 2, 1, 1)

        # hook up signals
        url_object.connect("notify::progress", self._progress_changed_cb)
        url_object.connect("notify::paused", self._paused_changed_cb)
        url_object.connect("notify::running", self._running_changed_cb)
        url_object.connect("notify::finished", self._finished_changed_cb)

    def _progress_changed_cb(self, url_object: URLObject, param):
        self._progress_bar.set_fraction(url_object.props.progress)
        self._status_label.props.label = (
            f"Download {url_object.props.progress:%} completed"
        )

    def _paused_changed_cb(self, url_object: URLObject, param):
        if url_object.props.paused:
            self._status_label.props.label = (
                f"Download paused at {url_object.props.progress:%} completed"
            )
        else:
            self._status_label.props.label = (
                f"Download {url_object.props.progress:%} completed"
            )

    def _running_changed_cb(self, url_object: URLObject, param):
        if url_object.props.running:
            self._status_label.props.label = (
                f"Download {url_object.props.progress:%} completed"
            )

    def _finished_changed_cb(self, url_object: URLObject, param):
        if url_object.props.finished:
            error_msg = url_object.get_error_message()
            if error_msg:
                logger.warning(
                    f"Download failed for {url_object.props.filename}: {error_msg}"
                )
                # TODO: make error message visible to user (tooltip??)
                self._status_label.props.label = f"Download failed!"
            else:
                self._status_label.props.label = f"Download completed!"
