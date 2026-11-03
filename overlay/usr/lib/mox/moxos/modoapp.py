"""Modo as a built-in MOX app with its own window and saved login."""
import sys
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("WebKit", "6.0")
from gi.repository import Adw, Gio, WebKit

from .common import config


def on_activate(app):
    window = app.get_active_window()
    if window is None:
        data = Path.home() / ".local/share/mox/modo"
        cache = Path.home() / ".cache/mox/modo"
        session = WebKit.NetworkSession.new(str(data), str(cache))
        view = WebKit.WebView(network_session=session, hexpand=True, vexpand=True)
        view.load_uri(config()["apps"]["modo_url"])
        toolbar = Adw.ToolbarView()
        toolbar.add_top_bar(Adw.HeaderBar())
        toolbar.set_content(view)
        window = Adw.ApplicationWindow(application=app, title="Modo", default_width=1280, default_height=820, content=toolbar)
    window.present()


def main():
    app = Adw.Application(application_id="org.mox.Modo", flags=Gio.ApplicationFlags.DEFAULT_FLAGS)
    app.connect("activate", on_activate)
    return app.run(sys.argv[:1])
