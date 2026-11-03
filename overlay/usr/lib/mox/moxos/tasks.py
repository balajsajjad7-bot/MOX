"""MOX Task Manager: apps, processes and performance at a glance."""
import os
import signal
import sys

import gi
import psutil

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib, Gtk


def top_processes(limit=60):
    rows = []
    for process in psutil.process_iter(["pid", "name", "username", "cpu_percent", "memory_info"]):
        info = process.info
        if info["memory_info"] is None:
            continue
        rows.append({"pid": info["pid"], "name": info["name"] or "?", "user": info["username"] or "",
                     "cpu": info["cpu_percent"] or 0.0, "memory_mb": info["memory_info"].rss / 1048576})
    return sorted(rows, key=lambda row: (row["cpu"], row["memory_mb"]), reverse=True)[:limit]


def can_end(row):
    return row["user"] == psutil.Process().username() and row["pid"] != os.getpid()


class Window(Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="MOX Task Manager", default_width=820, default_height=640)
        self.meters = {}
        stats = Gtk.Grid(column_spacing=12, row_spacing=12, column_homogeneous=True, margin_top=14, margin_start=14, margin_end=14)
        for index, key in enumerate(("CPU", "Memory", "Disk", "Network")):
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, css_classes=["card"])
            title = Gtk.Label(label=key, xalign=0, css_classes=["dim-label"], margin_top=10, margin_start=12)
            value = Gtk.Label(label="…", xalign=0, css_classes=["title-2"], margin_start=12)
            level = Gtk.LevelBar(margin_start=12, margin_end=12, margin_bottom=12)
            for widget in (title, value, level):
                box.append(widget)
            stats.attach(box, index, 0, 1, 1)
            self.meters[key] = (value, level)
        self.list = Gtk.ListBox(css_classes=["boxed-list"], margin_top=14, margin_bottom=14, margin_start=14, margin_end=14)
        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        body.append(stats)
        body.append(Gtk.ScrolledWindow(child=self.list, vexpand=True))
        toolbar = Adw.ToolbarView()
        toolbar.add_top_bar(Adw.HeaderBar())
        toolbar.set_content(body)
        self.set_content(toolbar)
        self.net = psutil.net_io_counters()
        psutil.cpu_percent()
        self.refresh()
        GLib.timeout_add_seconds(2, self.refresh)

    def refresh(self):
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage("/")
        net = psutil.net_io_counters()
        rate = (net.bytes_recv - self.net.bytes_recv + net.bytes_sent - self.net.bytes_sent) / 2 / 1048576
        self.net = net
        cpu = psutil.cpu_percent()
        values = {"CPU": (f"{cpu:.0f}%", cpu / 100), "Memory": (f"{memory.percent:.0f}%", memory.percent / 100),
                  "Disk": (f"{disk.percent:.0f}% full", disk.percent / 100), "Network": (f"{rate:.1f} MB/s", min(rate / 50, 1))}
        for key, (text, fraction) in values.items():
            self.meters[key][0].set_label(text)
            self.meters[key][1].set_value(fraction)
        while child := self.list.get_first_child():
            self.list.remove(child)
        for row in top_processes():
            item = Adw.ActionRow(title=GLib.markup_escape_text(row["name"]), subtitle=f"{row['cpu']:.0f}% CPU · {row['memory_mb']:.0f} MB · {row['user']}")
            if can_end(row):
                button = Gtk.Button(label="End", valign=Gtk.Align.CENTER, css_classes=["flat"])
                button.connect("clicked", lambda _b, pid=row["pid"]: self.end(pid))
                item.add_suffix(button)
            self.list.append(item)
        return True

    def end(self, pid):
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass


def main():
    app = Adw.Application(application_id="org.mox.Tasks", flags=Gio.ApplicationFlags.DEFAULT_FLAGS)
    Adw.StyleManager.get_default().set_color_scheme(Adw.ColorScheme.PREFER_DARK)
    app.connect("activate", lambda a: (a.get_active_window() or Window(a)).present())
    return app.run(sys.argv[:1])
