"""MOX Bot chat window."""
import sys
import threading

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib, Gtk

from . import bot


def bubble(text, mine):
    label = Gtk.Label(label=text, wrap=True, selectable=True, xalign=0, max_width_chars=64)
    frame = Gtk.Box(css_classes=["card"], halign=Gtk.Align.END if mine else Gtk.Align.START)
    label.set_margin_top(10)
    label.set_margin_bottom(10)
    label.set_margin_start(14)
    label.set_margin_end(14)
    frame.append(label)
    return frame, label


def on_activate(app):
    window = app.get_active_window()
    if window:
        window.present()
        return
    messages = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, margin_top=14, margin_bottom=14, margin_start=14, margin_end=14)
    scroller = Gtk.ScrolledWindow(child=messages, vexpand=True)
    messages.append(bubble(bot.HELP, False)[0])
    entry = Gtk.Entry(placeholder_text="Message MOX Bot", margin_top=8, margin_bottom=12, margin_start=14, margin_end=14)

    def send(widget):
        text = widget.get_text().strip()
        if not text:
            return
        widget.set_text("")
        messages.append(bubble(text, True)[0])
        frame, label = bubble("…", False)
        messages.append(frame)

        def work():
            answer = bot.reply(text)
            GLib.idle_add(label.set_label, answer)

        threading.Thread(target=work, daemon=True).start()

    entry.connect("activate", send)
    body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    body.append(scroller)
    body.append(entry)
    toolbar = Adw.ToolbarView()
    toolbar.add_top_bar(Adw.HeaderBar())
    toolbar.set_content(body)
    Adw.ApplicationWindow(application=app, title="MOX Bot", default_width=620, default_height=720, content=toolbar).present()


def main():
    app = Adw.Application(application_id="org.mox.Bot", flags=Gio.ApplicationFlags.DEFAULT_FLAGS)
    Adw.StyleManager.get_default().set_color_scheme(Adw.ColorScheme.PREFER_DARK)
    app.connect("activate", on_activate)
    return app.run(sys.argv[:1])
