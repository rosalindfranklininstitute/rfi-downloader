from __future__ import annotations

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gtk, Gdk, Gio, GLib

import logging
from typing import Optional, Final, List
import os
import urllib.parse
from threading import Thread
from pathlib import PurePosixPath

from .utils import (
    add_action_entries,
    EXPAND_AND_FILL,
    LongTaskWindow,
)
from .downloadmanager import DownloadManager
from .urlobject import URLObject
from .urllistboxrow import URLListBoxRow

logger = logging.getLogger(__name__)


class ApplicationWindow(Gtk.ApplicationWindow):
    def __init__(self, **kwargs):
        Gtk.ApplicationWindow.__init__(
            self,
            title="RFI-Downloader",
            default_height=750,
            default_width=750,
            border_width=10,
            type=Gtk.WindowType.TOPLEVEL,
            **kwargs,
        )

        action_entries = (
            ("close", self.on_close),
            ("minimize", self.on_minimize),
            ("play", self.on_play),
            ("pause", self.on_pause),
            ("stop", self.on_stop),
        )

        for action_entry in action_entries:
            add_action_entries(self, *action_entry)

        main_grid = Gtk.Grid(row_spacing=10, **EXPAND_AND_FILL)
        self.add(main_grid)

        controls_grid = Gtk.Grid(
            row_spacing=5,
            column_spacing=5,
            halign=Gtk.Align.FILL,
            valign=Gtk.Align.CENTER,
            hexpand=True,
            vexpand=False,
        )

        main_grid.attach(controls_grid, 0, 0, 1, 1)

        buttons_grid = Gtk.Grid(
            row_spacing=5,
            column_spacing=5,
            halign=Gtk.Align.START,
            valign=Gtk.Align.START,
            hexpand=False,
            vexpand=False,
        )

        controls_grid.attach(buttons_grid, 0, 0, 1, 2)

        play_button = Gtk.Button(
            action_name="win.play",
            image=Gtk.Image(
                icon_name="media-playback-start", icon_size=Gtk.IconSize.DIALOG
            ),
            halign=Gtk.Align.CENTER,
            valign=Gtk.Align.END,
            hexpand=False,
            vexpand=False,
        )
        buttons_grid.attach(play_button, 0, 0, 1, 1)

        pause_button = Gtk.Button(
            action_name="win.pause",
            image=Gtk.Image(
                icon_name="media-playback-pause", icon_size=Gtk.IconSize.DIALOG
            ),
            halign=Gtk.Align.CENTER,
            valign=Gtk.Align.CENTER,
            hexpand=False,
            vexpand=False,
        )
        buttons_grid.attach(pause_button, 0, 1, 1, 1)

        stop_button = Gtk.Button(
            action_name="win.stop",
            image=Gtk.Image(
                icon_name="media-playback-stop", icon_size=Gtk.IconSize.DIALOG
            ),
            halign=Gtk.Align.CENTER,
            valign=Gtk.Align.START,
            hexpand=False,
            vexpand=False,
        )
        buttons_grid.attach(stop_button, 0, 2, 1, 1)

        # turn the buttons off for now
        self.lookup_action("play").set_enabled(False)
        self.lookup_action("pause").set_enabled(False)
        self.lookup_action("stop").set_enabled(False)

        label = Gtk.Label(
            label="URLs File",
            halign=Gtk.Align.START,
            valign=Gtk.Align.CENTER,
            hexpand=False,
            vexpand=False,
        )
        controls_grid.attach(label, 1, 0, 1, 1)

        self._urls_file_button = Gtk.FileChooserButton(
            title="Select a file with URLs",
            action=Gtk.FileChooserAction.OPEN,
            halign=Gtk.Align.FILL,
            valign=Gtk.Align.CENTER,
            hexpand=True,
            vexpand=False,
        )
        filter = Gtk.FileFilter()
        filter.add_mime_type("text/plain")
        filter.set_name("Plain text files")
        self._urls_file_button.add_filter(filter)
        self._urls_file_button.connect(
            "selection-changed",
            self._on_urls_file_selection_changed,
        )
        controls_grid.attach(self._urls_file_button, 2, 0, 1, 1)

        label = Gtk.Label(
            label="Destination",
            halign=Gtk.Align.START,
            valign=Gtk.Align.CENTER,
            hexpand=False,
            vexpand=False,
        )
        controls_grid.attach(label, 1, 1, 1, 1)

        self._destination_button = Gtk.FileChooserButton(
            title="Select a location to store the files",
            action=Gtk.FileChooserAction.SELECT_FOLDER,
            halign=Gtk.Align.FILL,
            valign=Gtk.Align.CENTER,
            hexpand=True,
            vexpand=False,
        )
        self._destination_button.connect(
            "selection-changed",
            self._on_destination_selection_changed,
        )
        controls_grid.attach(self._destination_button, 2, 1, 1, 1)

        sw = Gtk.ScrolledWindow(**EXPAND_AND_FILL, shadow_type=Gtk.ShadowType.IN)
        lb = Gtk.ListBox(**EXPAND_AND_FILL)
        sw.add(lb)
        main_grid.attach(sw, 0, 1, 1, 1)

        self._filename: str = None
        self._destination: str = None
        self._download_manager: Final[DownloadManager] = DownloadManager(self)
        self._model: Final[Gio.ListStore] = Gio.ListStore(item_type=URLObject)

        lb.bind_model(model=self._model, create_widget_func=self._create_widget_func)

        self._download_manager.connect(
            "notify::paused", self._download_manager_paused_changed
        )

    def _create_widget_func(self, url_object: URLObject, *user_data):
        logger.debug(f"Calling _create_widget_func for {url_object.props.filename}")
        rv = URLListBoxRow(url_object)
        rv.show_all()
        return rv

    @property
    def download_manager(self):
        return self._download_manager

    @property
    def model(self):
        return self._model

    def _on_urls_file_selection_changed(self, button: Gtk.FileChooserButton):
        filename: Optional[str] = button.get_filename()
        if filename and os.path.isfile(filename) and os.access(filename, os.R_OK):
            self._filename = filename
        else:
            self._filename = None
        self._update_buttons()

    def _on_destination_selection_changed(self, button: Gtk.FileChooserButton):
        destination: Optional[str] = button.get_filename()
        if (
            destination
            and os.path.isdir(destination)
            and os.access(destination, os.W_OK)
        ):
            self._destination = destination
        else:
            self._destination = None
        self._update_buttons()

    def _update_buttons(self):
        if self._filename is not None and self._destination is not None:
            self.lookup_action("play").set_enabled(True)
        else:
            self.lookup_action("play").set_enabled(False)

    def on_play(self, action, param):
        self.lookup_action("play").set_enabled(False)

        if self._download_manager.props.paused:
            self.lookup_action("stop").set_enabled(False)
            self._download_manager.start()
            return

        self._urls_file_button.set_sensitive(False)
        self._destination_button.set_sensitive(False)
        task_window = LongTaskWindow(self)
        task_window.set_text("<b>Running preflight check</b>")
        task_window.show()
        watch_cursor = Gdk.Cursor.new_for_display(
            Gdk.Display.get_default(), Gdk.CursorType.WATCH
        )
        task_window.get_window().set_cursor(watch_cursor)

        self._model.remove_all()

        PreflightCheckThread(self, task_window).start()

    def on_pause(self, action, param):
        self.lookup_action("play").set_enabled(False)
        self.lookup_action("pause").set_enabled(False)
        self.lookup_action("stop").set_enabled(False)
        self._download_manager.pause()

    def _download_manager_paused_changed(self, download_manager, param):
        if download_manager.props.paused is True:
            self.lookup_action("play").set_enabled(True)
        else:
            self.lookup_action("pause").set_enabled(True)
        self.lookup_action("stop").set_enabled(True)

    def on_stop(self, action, param):
        self.lookup_action("stop").set_enabled(False)
        self.lookup_action("pause").set_enabled(False)
        self.lookup_action("play").set_enabled(False)
        self._download_manager.stop()

    def on_minimize(self, action, param):
        self.iconify()

    def on_close(self, action, param):
        self.close()

    def set_file(self, filename: str):
        self._filename = filename

    def _preflight_check_cb(
        self, task_window: LongTaskWindow, exception_msgs: Optional[List[str]]
    ):
        task_window.get_window().set_cursor(None)
        task_window.destroy()

        if exception_msgs:
            dialog = Gtk.MessageDialog(
                transient_for=self.get_toplevel(),
                modal=True,
                destroy_with_parent=True,
                message_type=Gtk.MessageType.ERROR,
                buttons=Gtk.ButtonsType.CLOSE,
                text="The following errors were encountered",
                secondary_text="\n".join(exception_msgs),
            )
            dialog.run()
            dialog.destroy()
            # if no valid urls were found, dont bother starting the download manager
            if not len(self._model):
                return

        self._download_manager_running_changed_handler_id = (
            self._download_manager.connect(
                "notify::running", self._download_manager_running_changed
            )
        )
        self._download_manager.start()

    def _download_manager_finished_changed(self, download_manager, param):
        if self._download_manager.props.finished:
            # deactivate stop and pause buttons
            self.lookup_action("play").set_enabled(False)
            self.lookup_action("stop").set_enabled(False)
            self.lookup_action("pause").set_enabled(False)
            self._download_manager.disconnect(
                self._download_manager_finished_changed_handler_id
            )

    def _download_manager_running_changed(self, download_manager, param):
        if self._download_manager.props.running:
            # hook up signal handler for finished
            self._download_manager_finished_changed_handler_id = (
                self._download_manager.connect(
                    "notify::finished", self._download_manager_finished_changed
                )
            )

            # activate stop and pause buttons
            self.lookup_action("stop").set_enabled(True)
            self.lookup_action("pause").set_enabled(True)

            self._download_manager.disconnect(
                self._download_manager_running_changed_handler_id
            )


class PreflightCheckThread(Thread):
    def __init__(self, appwindow: ApplicationWindow, task_window: LongTaskWindow):
        super().__init__()
        self._appwindow = appwindow
        self._task_window = task_window

    def run(self):
        exception_msgs = []

        # open URLs file
        with open(self._appwindow._filename, "r") as f:
            lines = f.readlines()

        # ignore empty lines and those starting with '#'
        def _filter(x: str) -> bool:
            x = x.strip()
            if not x or x.startswith("#"):
                return False
            return True

        lines = filter(_filter, lines)

        for line in lines:
            line = line.split()[0]  # ignore any rubbish following the url
            parsed = urllib.parse.urlparse(line)

            if parsed.scheme not in ("http", "https"):
                exception_msgs.append(
                    f"URL {line} does not follow the http or https scheme"
                )
                continue

            if not parsed.path:
                exception_msgs.append(f"URL {line} does not contain a path component")
                continue

            path = PurePosixPath(urllib.parse.unquote(parsed.path[1:]))
            destination_file = os.path.join(self._appwindow._destination, *path.parts)

            url_object = URLObject(
                url=line,
                filename=destination_file,
                relative_path=os.path.join(*path.parts),
            )
            logger.debug(f"Appending {url_object.props.filename}")
            self._appwindow.model.append(url_object)

        GLib.idle_add(
            self._appwindow._preflight_check_cb,
            self._task_window,
            exception_msgs,
            priority=GLib.PRIORITY_DEFAULT_IDLE,
        )
