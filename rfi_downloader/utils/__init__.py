from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Soup", "2.4")
from gi.repository import Gio, GLib, Gtk, Soup

from typing import (
    Callable,
    Optional,
    Final,
    Any,
    Dict,
    Union,
)
import logging
import os
import platform
from threading import Thread
import time
from pathlib import PurePath

EXPAND_AND_FILL: Final[Dict[str, Any]] = dict(
    hexpand=True, vexpand=True, halign=Gtk.Align.FILL, valign=Gtk.Align.FILL
)

logger = logging.getLogger(__name__)


def get_border_width(width: int) -> Dict[str, int]:
    """Replicates border_width parameter from Gtk3, by producing a dict equivalent margin parameters

    Args:
        width (int): the border width

    Returns:
        Dict[str, int]: the dict with margin parameters
    """
    return dict(
        margin_start=width,
        margin_end=width,
        margin_top=width,
        margin_bottom=width,
    )


def add_action_entries(
    map: Gio.ActionMap,
    action: str,
    callback: Callable[[Gio.ActionMap, Gio.SimpleAction, GLib.Variant], None],
    param: Optional[str] = None,
    state: Optional[GLib.Variant] = None,
    callback_arg: Optional[Any] = None,
) -> None:

    if state:
        simple_action = Gio.SimpleAction.new_stateful(
            action, GLib.VariantType.new(param) if param else None, state
        )
    else:
        simple_action = Gio.SimpleAction.new(
            action, GLib.VariantType.new(param) if param else None
        )

    if callback_arg:
        simple_action.connect("activate", callback, callback_arg)
    else:
        simple_action.connect("activate", callback)

    map.add_action(simple_action)


def get_file_creation_timestamp(file_path: Union[os.PathLike, str]):
    # get creation time, or something similar...
    # https://stackoverflow.com/a/39501288
    if platform.system() == "Windows":
        try:
            return os.stat(file_path).st_ctime
        except FileNotFoundError:
            time.sleep(1)
            try:
                return os.stat(file_path).st_ctime
            except FileNotFoundError:
                return None
    else:
        try:
            # this should work on macOS
            return os.stat(file_path).st_birthtime
        except AttributeError:
            return os.stat(file_path).st_mtime


class LongTaskWindow(Gtk.Window):
    def __init__(
        self, parent_window: Optional[Gtk.Window] = None, *args, **kwargs
    ):
        kwargs.update(
            dict(
                transient_for=parent_window,
                modal=True,
                default_width=250,
                default_height=100,
                destroy_with_parent=True,
                decorated=False,
            )
        )
        Gtk.Window.__init__(self, *args, **kwargs)
        main_grid = Gtk.Grid(
            column_spacing=10,
            row_spacing=10,
            **EXPAND_AND_FILL,
            **get_border_width(5),
        )
        self._label = Gtk.Label(wrap=True, **EXPAND_AND_FILL)
        main_grid.attach(self._label, 0, 0, 1, 1)
        label = Gtk.Label(
            label="This may take a while...",
        )
        main_grid.attach(label, 0, 1, 1, 1)
        self.set_child(main_grid)
        main_grid.show()

    def set_text(self, text: str):
        self._label.set_markup(text)


class ExitableThread(Thread):
    def __init__(self):
        super().__init__()
        self._should_exit: bool = False

    @property
    def should_exit(self):
        return self._should_exit

    @should_exit.setter
    def should_exit(self, value: bool):
        self._should_exit = value


class Session(Soup.Session):
    def __init__(self, **kwargs):
        super().__init__(use_thread_context=True, **kwargs)

        # Use conda OpenSSL certificates on Windows
        if os.name == "nt" and "CONDA_PREFIX" in os.environ:
            ca_file = PurePath(
                os.environ["CONDA_PREFIX"], "Library", "ssl", "cacert.pem"
            )
            try:
                db = Gio.TlsFileDatabase.new(str(ca_file))
            except GLib.Error as e:
                logger.warning(
                    f"Could not create TLS database for {str(ca_file)} -> {e.message}"
                )
            else:
                self.props.tls_database = db
                self.props.ssl_use_system_ca_file = False
