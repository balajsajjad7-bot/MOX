"""Opens a website as its own app window with a saved sign-in."""
import re
import sys
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("WebKit", "6.0")
from gi.repository import Adw, Gio, WebKit

CHROME = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"


def slug(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def main():
    name, url = sys.argv[1], sys.argv[2]
    key = slug(name)

    def on_activate(app):
        window = app.get_active_window()
        if window is None:
            session = WebKit.NetworkSession.new(str(Path.home() / f".local/share/mox/apps/{key}"), str(Path.home() / f".cache/mox/apps/{key}"))
            view = WebKit.WebView(network_session=session, hexpand=True, vexpand=True)
            view.get_settings().set_user_agent(CHROME)
            view.load_uri(url)
            toolbar = Adw.ToolbarView()
            toolbar.add_top_bar(Adw.HeaderBar())
            toolbar.set_content(view)
            window = Adw.ApplicationWindow(application=app, title=name, default_width=1200, default_height=820, content=toolbar)
        window.present()

    app = Adw.Application(application_id=f"org.mox.app.{key.replace('-', '')}", flags=Gio.ApplicationFlags.NON_UNIQUE)
    app.connect("activate", on_activate)
    return app.run(sys.argv[:1])
