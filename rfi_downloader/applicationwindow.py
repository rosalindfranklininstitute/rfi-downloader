from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gtk, Gio, GLib, Pango

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
    get_border_width,
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

        menu_button = Gtk.MenuButton(
            valign=Gtk.Align.CENTER,
            focus_on_click=False,
            icon_name="open-menu-symbolic",
            menu_model=self.props.application.menu_model,
        )
        titlebar: Gtk.HeaderBar = Gtk.HeaderBar(
            title_widget=Gtk.Label(label="RFI-Downloader")
        )
        titlebar.pack_end(menu_button)
        self.set_titlebar(titlebar)

        main_grid = Gtk.Grid(row_spacing=10, **EXPAND_AND_FILL)
        self.set_child(main_grid)

        self._info_bar = Gtk.InfoBar(
            revealed=False,
            message_type=Gtk.MessageType.QUESTION,
            hexpand=True,
            vexpand=False,
            halign=Gtk.Align.FILL,
            valign=Gtk.Align.CENTER,
            **get_border_width(2),
        )
        self._info_bar.add_button("Ok", Gtk.ResponseType.OK)
        self._info_bar.add_button("Cancel", Gtk.ResponseType.CANCEL)
        label = Gtk.Label(
            **EXPAND_AND_FILL,
            use_markup=True,
            label="<b>Files are still being downloaded!</b>\n"
            + "Are you sure you want to close this window?",
        )
        self._info_bar.add_child(label)

        main_grid.attach(self._info_bar, 0, 0, 1, 1)

        controls_grid = Gtk.Grid(
            row_spacing=5,
            column_spacing=5,
            halign=Gtk.Align.FILL,
            valign=Gtk.Align.CENTER,
            hexpand=True,
            vexpand=False,
            **get_border_width(10),
        )

        main_grid.attach(controls_grid, 0, 1, 1, 1)

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
            halign=Gtk.Align.CENTER,
            valign=Gtk.Align.END,
            hexpand=False,
            vexpand=False,
        )
        icon = Gtk.Image(
            icon_name="media-playback-start", icon_size=Gtk.IconSize.LARGE
        )
        play_button.set_child(icon)
        buttons_grid.attach(play_button, 0, 0, 1, 1)

        pause_button = Gtk.Button(
            action_name="win.pause",
            halign=Gtk.Align.CENTER,
            valign=Gtk.Align.CENTER,
            hexpand=False,
            vexpand=False,
        )
        icon = Gtk.Image(
            icon_name="media-playback-pause", icon_size=Gtk.IconSize.LARGE
        )
        pause_button.set_child(icon)
        buttons_grid.attach(pause_button, 0, 1, 1, 1)

        stop_button = Gtk.Button(
            action_name="win.stop",
            halign=Gtk.Align.CENTER,
            valign=Gtk.Align.START,
            hexpand=False,
            vexpand=False,
        )
        icon = Gtk.Image(
            icon_name="media-playback-stop", icon_size=Gtk.IconSize.LARGE
        )
        stop_button.set_child(icon)
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

        self._urls_file_button = Gtk.Button(
            child=Gtk.Label(
                label="Select a file with URLs",
                ellipsize=Pango.EllipsizeMode.START,
            ),
            halign=Gtk.Align.FILL,
            valign=Gtk.Align.CENTER,
            hexpand=True,
            vexpand=False,
        )
        self._urls_file_button.connect(
            "clicked",
            self._open_urls_file_chooser_cb,
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

        self._destination_button = Gtk.Button(
            child=Gtk.Label(
                label="Select a location to store the files",
                ellipsize=Pango.EllipsizeMode.START,
            ),
            halign=Gtk.Align.FILL,
            valign=Gtk.Align.CENTER,
            hexpand=True,
            vexpand=False,
        )
        self._destination_button.connect(
            "clicked",
            self._open_destination_file_chooser_cb,
        )
        controls_grid.attach(self._destination_button, 2, 1, 1, 1)

        sw = Gtk.ScrolledWindow(**EXPAND_AND_FILL, has_frame=True)
        lb = Gtk.ListBox(**EXPAND_AND_FILL)
        sw.set_child(lb)
        main_grid.attach(sw, 0, 2, 1, 1)

        self._filename: str = None
        self._destination: str = None
        self._download_manager: Final[DownloadManager] = DownloadManager(self)
        self._model: Final[Gio.ListStore] = Gio.ListStore(item_type=URLObject)

        lb.bind_model(
            model=self._model, create_widget_func=self._create_widget_func
        )

        self._download_manager.connect(
            "notify::paused", self._download_manager_paused_changed
        )

        # connect delete-event signal handler
        self.connect("close-request", self._delete_event_cb)

    def _open_urls_file_chooser_cb(self, button: Gtk.Button):
        _filter = Gtk.FileFilter()
        _filter.add_mime_type("text/plain")
        _filter.set_name("Plain text files")

        dialog = Gtk.FileChooserNative(
            action=Gtk.FileChooserAction.OPEN,
            filter=_filter,
            title="Select a file with URLs",
            modal=True,
            transient_for=self.props.root,
        )
        dialog.connect(
            "response",
            self._urls_file_chooser_response_cb,
            button,
        )
        dialog.show()

    def _open_destination_file_chooser_cb(self, button: Gtk.Button):
        dialog = Gtk.FileChooserNative(
            action=Gtk.FileChooserAction.SELECT_FOLDER,
            title="Select a location to store the files",
            modal=True,
            transient_for=self.props.root,
        )
        dialog.connect(
            "response",
            self._destination_file_chooser_response_cb,
            button,
        )
        dialog.show()

    def _urls_file_chooser_response_cb(
        self,
        native: Gtk.FileChooserNative,
        response: int,
        button: Gtk.Button,
    ):
        if response == Gtk.ResponseType.ACCEPT:
            file: Gio.File = native.get_file()
            filename: str = file.get_path()
            if (
                filename
                and os.path.isfile(filename)
                and os.access(filename, os.R_OK)
            ):
                label: Gtk.Label = button.get_child()
                label.set_text(filename)
                self._filename = filename
            else:
                self._filename = None
            self._update_buttons()

        native.destroy()

    def _destination_file_chooser_response_cb(
        self,
        native: Gtk.FileChooserNative,
        response: int,
        button: Gtk.Button,
    ):
        if response == Gtk.ResponseType.ACCEPT:
            file: Gio.File = native.get_file()
            filename: str = file.get_path()
            if (
                filename
                and os.path.isdir(filename)
                and os.access(filename, os.W_OK)
            ):
                label: Gtk.Label = button.get_child()
                label.set_text(filename)
                self._destination = filename
            else:
                self._destination = None
            self._update_buttons()

        native.destroy()

    def _create_widget_func(self, url_object: URLObject, *user_data):
        logger.debug(
            f"Calling _create_widget_func for {url_object.props.filename}"
        )
        rv = URLListBoxRow(url_object)
        rv.show()
        return rv

    def _delete_event_dialog_timeout(self):
        if self._download_manager.props.running:
            return GLib.SOURCE_CONTINUE

        self._info_bar.response(Gtk.ResponseType.CANCEL)

        return GLib.SOURCE_REMOVE

    def _delete_event_killer(self, download_manager, _):
        logger.debug("Calling _delete_event_killer")
        if download_manager.props.running is False:
            self.destroy()

    def _delete_event_cb(self, window):
        # If nothing is running, just close it down
        if not self._download_manager.props.running:
            return False
        elif self._info_bar.props.revealed:
            return True

        # else, pop up an InfoBar asking for confirmation
        self._info_bar.props.revealed = True

        source_id = GLib.timeout_add_seconds(
            1,
            self._delete_event_dialog_timeout,
        )

        def _delete_event_dialog_response_cb(
            info_bar: Gtk.InfoBar, response: int
        ):
            GLib.source_remove(source_id)
            info_bar.disconnect(self._delete_event_dialog_response_handler_id)
            self._info_bar.props.revealed = False
            if response == Gtk.ResponseType.CANCEL:
                return
            elif response == Gtk.ResponseType.OK:
                if self._download_manager.props.running:
                    self._download_manager.disconnect(
                        self._download_manager_finished_changed_handler_id
                    )
                    # hookup signal to downloadmanager running property
                    self._download_manager.connect(
                        "notify::running", self._delete_event_killer
                    )
                    # stop it manually
                    self._download_manager.stop()

        self._delete_event_dialog_response_handler_id = self._info_bar.connect(
            "response", _delete_event_dialog_response_cb
        )

        return True

    @property
    def download_manager(self):
        return self._download_manager

    @property
    def model(self):
        return self._model

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
        task_window.set_cursor_from_name("wait")

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
        self.minimize()

    def on_close(self, action, param):
        self.close()

    def set_file(self, filename: str):
        self._filename = filename

    def _preflight_check_cb(
        self,
        task_window: LongTaskWindow,
        url_objects: List[URLObject],
        exception_msgs: Optional[List[str]],
    ):
        task_window.set_cursor(None)
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

            def _exception_messages_dialog_cb(dialog, response):
                dialog.destroy()
                # if no valid urls were found, dont bother starting the download manager
                if not len(url_objects):
                    return
                self._download_manager_start(url_objects)

            dialog.connect("response", _exception_messages_dialog_cb)

        self._download_manager_start(url_objects)

    def _download_manager_start(self, url_objects: List[URLObject]):
        for url_object in url_objects:
            self._model.append(url_object)

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
    def __init__(
        self, appwindow: ApplicationWindow, task_window: LongTaskWindow
    ):
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
        url_objects: List[URLObject] = list()

        for line in lines:
            line = line.split()[0]  # ignore any rubbish following the url
            parsed = urllib.parse.urlparse(line)

            if parsed.scheme not in ("http", "https"):
                exception_msgs.append(
                    f"URL {line} does not follow the http or https scheme"
                )
                continue

            if not parsed.path:
                exception_msgs.append(
                    f"URL {line} does not contain a path component"
                )
                continue

            path = PurePosixPath(urllib.parse.unquote(parsed.path[1:]))
            destination_file = os.path.join(
                self._appwindow._destination, *path.parts
            )

            url_object = URLObject(
                url=line,
                filename=destination_file,
                relative_path=os.path.join(*path.parts),
            )
            logger.debug(f"Appending {url_object.props.filename}")
            url_objects.append(url_object)

        GLib.idle_add(
            self._appwindow._preflight_check_cb,
            self._task_window,
            url_objects,
            exception_msgs,
            priority=GLib.PRIORITY_DEFAULT_IDLE,
        )
