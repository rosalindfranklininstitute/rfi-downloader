from __future__ import annotations

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gio, Gtk, GdkPixbuf

import importlib.resources
import platform
import webbrowser
import logging
import importlib.metadata
from pathlib import Path

from .version import __version__
from .utils import add_action_entries
from .utils.googleanalytics import GoogleAnalyticsContext

from .applicationwindow import ApplicationWindow

logger = logging.getLogger(__name__)


class Application(Gtk.Application):
    def __init__(self, *args, **kwargs):
        super().__init__(
            *args,
            application_id="uk.ac.rfi.ai.downloader",
            flags=Gio.ApplicationFlags.FLAGS_NONE,
            **kwargs,
        )
        GLib.set_application_name("RFI Downloader")

    @property
    def google_analytics_context(self):
        return self._google_analytics_context

    def do_shutdown(self):
        Gtk.Application.do_shutdown(self)

        self._google_analytics_context.consumer_thread.should_exit = True

    def do_startup(self):
        Gtk.Application.do_startup(self)

        # acquire google analytics context
        self._google_analytics_context = GoogleAnalyticsContext(
            endpoint="https://www.google-analytics.com/collect",
            tracking_id="UA-184737687-2",
            application_name="RFI-Downloader",
            application_version=__version__,
            config_file=Path(GLib.get_user_config_dir(), "rfi-downloader", "ga.conf"),
        )

        # send event to Google Analytics
        self._google_analytics_context.send_event(
            "LAUNCH",
            "Downloader-{}-Python-{}-{}".format(
                __version__, platform.python_version(), platform.platform()
            ),
            None,
        )

        # this may need to be checked on other platforms as well
        if platform.system() == "Darwin":
            appmenus_str = importlib.resources.read_text(
                "rfi_downloader.data", "menus-appmenu.ui"
            )
            builder = Gtk.Builder.new_from_string(appmenus_str, -1)
            self.set_app_menu(builder.get_object("app-menu"))

        commonmenus_str = importlib.resources.read_text(
            "rfi_downloader.data", "menus-common.ui"
        )
        builder = Gtk.Builder.new_from_string(commonmenus_str, -1)
        self.set_menubar(builder.get_object("menubar"))

        action_entries = (
            ("about", self.on_about),
            ("quit", self.on_quit),
            ("open", self.on_open),
            ("new", lambda *_: self.do_activate()),
            ("help-url", self.on_help_url, "s"),
        )

        for action_entry in action_entries:
            add_action_entries(self, *action_entry)

        # add accelerators
        accelerators = (
            ("app.quit", ("<Primary>Q",)),
            ("app.new", ("<Primary>N",)),
            ("app.open", ("<Primary>O",)),
            ("win.close", ("<Primary>W",)),
        )

        for accel in accelerators:
            self.set_accels_for_action(accel[0], accel[1])

    def on_open(self, action, param):
        # fire up file chooser dialog
        active_window = self.get_active_window()
        dialog = Gtk.FileChooserNative(
            modal=True,
            title="Open file with URLs",
            transient_for=active_window,
            action=Gtk.FileChooserAction.OPEN,
        )
        filter = Gtk.FileFilter()
        # TODO: add mime filter
        filter.set_name("Plain text files")
        dialog.add_filter(filter)

        if dialog.run() == Gtk.ResponseType.ACCEPT:
            urls_file = dialog.get_filename()
            dialog.destroy()
            try:
                # TODO: open file
                pass
            except Exception as e:
                dialog = Gtk.MessageDialog(
                    transient_for=active_window,
                    modal=True,
                    destroy_with_parent=True,
                    message_type=Gtk.MessageType.ERROR,
                    buttons=Gtk.ButtonsType.CLOSE,
                    text=f"Could not load {urls_file}",
                    secondary_text=str(e),
                )
                dialog.run()
                dialog.destroy()
            else:
                window = ApplicationWindow(
                    application=self,
                    type=Gtk.WindowType.TOPLEVEL,
                    force_all=True,
                )
                window.show_all()
                # window.load_from_yaml_dict(yaml_dict)
        else:
            dialog.destroy()

    def do_activate(self):
        window = ApplicationWindow(application=self)
        window.show_all()

    def on_about(self, action, param):

        with importlib.resources.path(
            "rfi_downloader.data", "RFI-logo-transparent.png"
        ) as f:
            logo = GdkPixbuf.Pixbuf.new_from_file_at_scale(str(f), 300, -1, True)

        about_dialog = Gtk.AboutDialog(
            transient_for=self.get_active_window(),
            modal=True,
            authors=["Tom Schoonjans"],
            logo=logo,
            version=__version__,
        )
        about_dialog.present()

    def on_quit(self, action, param):
        windows = filter(
            lambda window: isinstance(window, ApplicationWindow),
            self.get_windows(),
        )

        for window in windows:
            if window.download_manager.props.running:
                window.close()
            else:
                self.remove_window(window)

    def on_help_url(self, action, param):
        webbrowser.open_new_tab(param.get_string())
