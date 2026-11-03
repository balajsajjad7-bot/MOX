"""MOX News window."""
import subprocess
import sys
import threading

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib, Gtk

from . import news


def fill(page, results):
    for name, items in results.items():
        group = Adw.PreferencesGroup(title=name)
        page.add(group)
        if not items:
            group.add(Adw.ActionRow(title="Couldn't load this source"))
        for item in items:
            row = Adw.ActionRow(title=GLib.markup_escape_text(item["title"]), activatable=True)
            row.connect("activated", lambda _r, link=item["link"]: subprocess.Popen(["xdg-open", link]))
            group.add(row)


def on_activate(app):
    window = app.get_active_window()
    if window:
        window.present()
        return
    page = Adw.PreferencesPage()
    toolbar = Adw.ToolbarView()
    toolbar.add_top_bar(Adw.HeaderBar())
    toolbar.set_content(page)
    Adw.ApplicationWindow(application=app, title="MOX News", default_width=760, default_height=720, content=toolbar).present()
    threading.Thread(target=lambda: GLib.idle_add(fill, page, news.all_sources()), daemon=True).start()


def main():
    app = Adw.Application(application_id="org.mox.News", flags=Gio.ApplicationFlags.DEFAULT_FLAGS)
    Adw.StyleManager.get_default().set_color_scheme(Adw.ColorScheme.PREFER_DARK)
    app.connect("activate", on_activate)
    return app.run(sys.argv[:1])
