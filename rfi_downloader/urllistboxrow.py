from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Pango, Gio

from .urlobject import URLObject
from .utils import EXPAND_AND_FILL, get_border_width

import logging

logger = logging.getLogger(__name__)


class URLListBoxRow(Gtk.ListBoxRow):
    def __init__(self, url_object: URLObject):
        super().__init__(
            hexpand=True,
            vexpand=False,
            halign=Gtk.Align.FILL,
            valign=Gtk.Align.CENTER,
            activatable=False,
            has_tooltip=True,
        )

        self._url_object = url_object

        frame = Gtk.Frame(
            **EXPAND_AND_FILL,
            **get_border_width(2),
        )
        grid = Gtk.Grid(
            **EXPAND_AND_FILL,
            **get_border_width(2),
            column_spacing=4,
            row_spacing=2,
        )
        frame.set_child(grid)
        self.set_child(frame)

        self._image: Gtk.Image = Gtk.Image(
            icon_name="emblem-downloads",
            icon_size=Gtk.IconSize.LARGE,
            hexpand=False,
            vexpand=True,
            halign=Gtk.Align.START,
            valign=Gtk.Align.CENTER,
            name="color_image",
        )
        grid.attach(
            self._image,
            0,
            0,
            1,
            3,
        )

        grid.attach(
            Gtk.Label(
                label=f"<b>{url_object.props.relative_path}</b>",
                use_markup=True,
                ellipsize=Pango.EllipsizeMode.START,
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
            ellipsize=Pango.EllipsizeMode.START,
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
        self._status_label.props.label = url_object.get_status_message()

    def _paused_changed_cb(self, url_object: URLObject, param):
        if url_object.props.paused:
            self._status_label.props.label = (
                f"Paused at {url_object.props.progress:%} completed"
            )
        else:
            self._status_label.props.label = url_object.get_status_message()

    def _running_changed_cb(self, url_object: URLObject, param):
        if url_object.props.running:
            self._status_label.props.label = "Starting..."
            ctxt: Gtk.StyleContext = self._image.get_style_context()
            ctxt.add_class("orange")

    def _finished_changed_cb(self, url_object: URLObject, param):
        if url_object.props.finished:
            error_msg = url_object.get_error_message()
            self._image.remove_css_class("orange")
            ga_ctxt = Gio.Application.get_default().google_analytics_context
            if error_msg:
                logger.info(
                    f"Download failed for {url_object.props.filename}: {error_msg}"
                )
                # TODO: make error message visible to user (tooltip??)
                self._status_label.props.label = f"Download failed!"
                self.props.tooltip_text = error_msg
                self._image.add_css_class("red")
                ga_ctxt.send_event("DOWNLOAD-FILE", "FAILURE")
            else:
                self._image.add_css_class("green")
                ga_ctxt.send_event("DOWNLOAD-FILE", "SUCCESS")

    def do_query_tooltip(self, x, y, keyboard_mode, tooltip: Gtk.Tooltip):
        if (error_msg := self._url_object.get_error_message()) is None:
            return False

        tooltip.set_icon_from_icon_name("network-error")
        tooltip.set_text(error_msg)

        return True
