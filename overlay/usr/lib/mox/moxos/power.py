"""MOX Power: a calm full-screen menu for lock, sleep, restart and shut down."""
import subprocess
import sys

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, Gtk

CSS = """
window.mox-power { background-color: rgba(8, 8, 12, 0.72); }
.mox-round { min-width: 92px; min-height: 92px; border-radius: 46px; background-color: rgba(255,255,255,0.10); border: 1px solid rgba(255,255,255,0.14); }
.mox-round:hover { background-color: rgba(255,255,255,0.22); }
.mox-round image { -gtk-icon-size: 34px; }
.mox-caption { color: rgba(255,255,255,0.86); font-size: 14px; }
.mox-power-title { color: white; font-size: 28px; font-weight: 300; letter-spacing: 6px; }
"""
ACTIONS = [
    ("Lock", "system-lock-screen-symbolic", ["loginctl", "lock-session"]),
    ("Sleep", "weather-clear-night-symbolic", ["systemctl", "suspend"]),
    ("Restart", "system-reboot-symbolic", ["systemctl", "reboot"]),
    ("Shut Down", "system-shutdown-symbolic", ["systemctl", "poweroff"]),
    ("Log Out", "system-log-out-symbolic", ["gnome-session-quit", "--logout", "--no-prompt"]),
]


def on_activate(app):
    provider = Gtk.CssProvider()
    provider.load_from_string(CSS)
    Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
    window = Gtk.ApplicationWindow(application=app, css_classes=["mox-power"], decorated=False)
    row = Gtk.Box(spacing=34, halign=Gtk.Align.CENTER)
    for label, icon, command in ACTIONS:
        column = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        button = Gtk.Button(icon_name=icon, css_classes=["mox-round"], halign=Gtk.Align.CENTER)
        button.connect("clicked", lambda _b, cmd=command: (window.close(), subprocess.Popen(cmd)))
        column.append(button)
        column.append(Gtk.Label(label=label, css_classes=["mox-caption"]))
        row.append(column)
    cancel = Gtk.Button(label="Cancel", css_classes=["pill"], halign=Gtk.Align.CENTER)
    cancel.connect("clicked", lambda _b: window.close())
    body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=40, valign=Gtk.Align.CENTER)
    body.append(Gtk.Label(label="M O X", css_classes=["mox-power-title"]))
    body.append(row)
    body.append(cancel)
    keys = Gtk.EventControllerKey()
    keys.connect("key-pressed", lambda _c, key, _code, _state: key == Gdk.KEY_Escape and (window.close() or True))
    window.add_controller(keys)
    window.set_child(body)
    window.fullscreen()
    window.present()


def main():
    app = Adw.Application(application_id="org.mox.Power", flags=Gio.ApplicationFlags.DEFAULT_FLAGS)
    app.connect("activate", on_activate)
    return app.run(sys.argv[:1])
