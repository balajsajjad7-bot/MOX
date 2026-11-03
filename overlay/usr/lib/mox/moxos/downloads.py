"""MOX Downloader: fast, resumable downloads with aria2."""
import re
import subprocess
import sys
import threading
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib, Gtk

FOLDER = Path.home() / "Downloads"
PROGRESS = re.compile(r"\[#\w+ ([\d.]+\w+)/([\d.]+\w+)\((\d+)%\).*?DL:([\d.]+\w+)(?: ETA:(\w+))?")


def parse_progress(line):
    match = PROGRESS.search(line)
    if not match:
        return None
    return {"done": match[1], "total": match[2], "percent": int(match[3]), "speed": match[4] + "/s", "eta": match[5] or ""}


def command(url):
    if not re.match(r"^(https?|ftp|magnet):", url):
        raise ValueError("Paste a link that starts with http, https, ftp or magnet.")
    return ["aria2c", "--continue=true", "--max-connection-per-server=8", "--split=8", "--summary-interval=1",
            "--console-log-level=warn", "--seed-time=0", f"--dir={FOLDER}", url]


class Window(Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="MOX Downloader", default_width=720, default_height=520)
        self.entry = Gtk.Entry(hexpand=True, placeholder_text="Paste a download link")
        self.entry.connect("activate", self.add)
        add = Gtk.Button(label="Download", css_classes=["suggested-action"])
        add.connect("clicked", self.add)
        bar = Gtk.Box(spacing=8, margin_top=14, margin_start=14, margin_end=14)
        bar.append(self.entry)
        bar.append(add)
        self.error = Gtk.Label(xalign=0, margin_start=14, css_classes=["error"])
        self.list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, margin_top=10, margin_bottom=14, margin_start=14, margin_end=14)
        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        body.append(bar)
        body.append(self.error)
        body.append(Gtk.ScrolledWindow(child=self.list, vexpand=True))
        toolbar = Adw.ToolbarView()
        header = Adw.HeaderBar()
        folder = Gtk.Button(icon_name="folder-download-symbolic", tooltip_text="Open Downloads")
        folder.connect("clicked", lambda _b: subprocess.Popen(["xdg-open", str(FOLDER)]))
        header.pack_end(folder)
        toolbar.add_top_bar(header)
        toolbar.set_content(body)
        self.set_content(toolbar)

    def add(self, _widget):
        url = self.entry.get_text().strip()
        try:
            args = command(url)
        except ValueError as error:
            self.error.set_label(str(error))
            return
        self.error.set_label("")
        self.entry.set_text("")
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, css_classes=["card"])
        name = Gtk.Label(label=url.rsplit("/", 1)[-1][:80] or url[:80], xalign=0, margin_top=10, margin_start=12, margin_end=12)
        bar = Gtk.ProgressBar(margin_start=12, margin_end=12)
        status = Gtk.Label(label="Starting…", xalign=0, css_classes=["dim-label"], margin_bottom=10, margin_start=12)
        for widget in (name, bar, status):
            card.append(widget)
        self.list.prepend(card)
        FOLDER.mkdir(exist_ok=True)
        process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

        def read():
            for line in process.stdout:
                info = parse_progress(line)
                if info:
                    GLib.idle_add(bar.set_fraction, info["percent"] / 100)
                    GLib.idle_add(status.set_label, f"{info['done']} of {info['total']} · {info['speed']} · {info['eta']} left")
            code = process.wait()
            GLib.idle_add(bar.set_fraction, 1.0 if code == 0 else bar.get_fraction())
            GLib.idle_add(status.set_label, "Done" if code == 0 else "Stopped. Paste the link again to resume.")

        threading.Thread(target=read, daemon=True).start()


def main():
    app = Adw.Application(application_id="org.mox.Downloader", flags=Gio.ApplicationFlags.DEFAULT_FLAGS)
    Adw.StyleManager.get_default().set_color_scheme(Adw.ColorScheme.PREFER_DARK)
    app.connect("activate", lambda a: (a.get_active_window() or Window(a)).present())
    return app.run(sys.argv[:1])
