from __future__ import annotations

import gi

gi.require_version("Gdk", "4.0")
gi.require_version("Gtk", "4.0")
from gi.repository import GLib, Gio, Gtk, GdkPixbuf, Gdk

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

        # load CSS data
        display: Gdk.Display = Gdk.Display.get_default()
        gtk_provider: Gtk.CssProvider = Gtk.CssProvider()
        Gtk.StyleContext.add_provider_for_display(
            display, gtk_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        try:
            gtk_provider.load_from_data(
                """
                .large-icons {-gtk-icon-size: 48px;}
                window.aboutdialog image.large-icons {-gtk-icon-size: 300px;}
		        #color_image.red { background-image: linear-gradient(red,red); }
		        #color_image.orange { background-image: linear-gradient(orange,orange); }
		        #color_image.green { background-image: linear-gradient(green,green); }
                """.encode(
                    "utf-8"
                )
            )
        except GLib.Error as e:
            logger.warning(f"Could not load CSS data: {e.message}")

        # acquire google analytics context
        self._google_analytics_context = GoogleAnalyticsContext(
            endpoint="https://www.google-analytics.com/collect",
            tracking_id="UA-184737687-2",
            application_name="RFI-Downloader",
            application_version=__version__,
            config_file=Path(
                GLib.get_user_config_dir(), "rfi-downloader", "ga.conf"
            ),
        )

        # send event to Google Analytics
        self._google_analytics_context.send_event(
            "LAUNCH",
            "Downloader-{}-Python-{}-{}".format(
                __version__, platform.python_version(), platform.platform()
            ),
            None,
        )

        commonmenus_str = importlib.resources.read_text(
            "rfi_downloader.data", "menus-common.ui"
        )
        builder = Gtk.Builder.new_from_string(commonmenus_str, -1)
        self._menu_model = builder.get_object("menubar")

        action_entries = (
            ("about", self.on_about),
            ("quit", self.on_quit),
            ("new", lambda *_: self.do_activate()),
            ("help-url", self.on_help_url, "s"),
        )

        for action_entry in action_entries:
            add_action_entries(self, *action_entry)

        # add accelerators
        accelerators = (
            ("app.quit", ("<Meta>Q",)),
            ("app.new", ("<Meta>N",)),
            ("win.close", ("<Meta>W",)),
        )

        for accel in accelerators:
            self.set_accels_for_action(accel[0], accel[1])

    @property
    def menu_model(self):
        return self._menu_model

    def do_activate(self):
        window = ApplicationWindow(application=self)
        window.show()

    def on_about(self, action, param):

        with importlib.resources.path(
            "rfi_downloader.data", "RFI-logo-transparent.png"
        ) as f:
            logo = GdkPixbuf.Pixbuf.new_from_file_at_scale(
                str(f), 300, -1, True
            )
            logo = Gdk.Texture.new_for_pixbuf(logo)

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
