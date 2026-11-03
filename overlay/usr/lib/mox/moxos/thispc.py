"""This PC: every drive in one window, like My Computer."""
import subprocess
import sys

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib, Gtk

from . import cloud, drives


def open_path(path):
    subprocess.Popen(["nautilus", str(path)])


def terminal(command):
    subprocess.Popen(["ptyxis", "--new-window", "--", "bash", "-c", f"{command}; echo; read -r -p 'Press Enter to close'"])


class Window(Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="This PC", default_width=820, default_height=640)
        self.page = Adw.PreferencesPage()
        toolbar = Adw.ToolbarView()
        header = Adw.HeaderBar()
        create = Gtk.Button(label="Create Drive")
        create.connect("clicked", lambda _b: subprocess.Popen(["gnome-disks"]))
        refresh = Gtk.Button(icon_name="view-refresh-symbolic")
        refresh.connect("clicked", lambda _b: self.fill())
        header.pack_start(create)
        header.pack_end(refresh)
        toolbar.add_top_bar(header)
        toolbar.set_content(self.page)
        self.set_content(toolbar)
        self.groups = []
        self.fill()

    def group(self, title):
        group = Adw.PreferencesGroup(title=title)
        self.page.add(group)
        self.groups.append(group)
        return group

    def fill(self):
        for group in self.groups:
            self.page.remove(group)
        self.groups = []
        items = drives.list_drives()
        local = self.group("Drives")
        for item in [entry for entry in items if not entry["removable"]] or []:
            local.add(self.row(item, "drive-harddisk-symbolic"))
        removable = [entry for entry in items if entry["removable"]]
        if removable:
            usb = self.group("Removable drives")
            for item in removable:
                usb.add(self.row(item, "drive-removable-media-symbolic"))
        online = self.group("Cloud drives")
        linked = cloud.connected()
        for service, (label, _backend) in cloud.REMOTES.items():
            row = Adw.ActionRow(title=label, subtitle="Connected" if service in linked else "Not connected")
            row.add_prefix(Gtk.Image(icon_name="folder-remote-symbolic"))
            button = Gtk.Button(label="Open" if service in linked else "Connect", valign=Gtk.Align.CENTER)
            if service in linked:
                button.connect("clicked", lambda _b, name=label: open_path(cloud.DRIVES / name))
            else:
                button.connect("clicked", lambda _b, name=service: terminal(f"mox cloud add {name}"))
            row.add_suffix(button)
            online.add(row)

    def row(self, item, icon):
        row = Adw.ActionRow(title=item["name"], subtitle=item["text"])
        row.add_prefix(Gtk.Image(icon_name=icon))
        bar = Gtk.LevelBar(value=item["fraction"], valign=Gtk.Align.CENTER, width_request=150)
        row.add_suffix(bar)
        button = Gtk.Button(label="Open", valign=Gtk.Align.CENTER)

        def on_open(_button):
            if item["mountpoint"]:
                open_path(item["mountpoint"])
            else:
                subprocess.run(["udisksctl", "mount", "-b", item["device"]], check=False)
                GLib.idle_add(self.fill)

        button.connect("clicked", on_open)
        row.add_suffix(button)
        return row


def on_activate(app):
    (app.get_active_window() or Window(app)).present()


def main():
    app = Adw.Application(application_id="org.mox.ThisPC", flags=Gio.ApplicationFlags.DEFAULT_FLAGS)
    Adw.StyleManager.get_default().set_color_scheme(Adw.ColorScheme.PREFER_DARK)
    app.connect("activate", on_activate)
    return app.run(sys.argv[:1])
