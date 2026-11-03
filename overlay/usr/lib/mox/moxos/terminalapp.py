"""MOX Terminal: a friendly terminal with buttons and plain-language help."""
import os
import shlex
import shutil
import subprocess
import sys

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
try:
    gi.require_version("Vte", "3.91")
    from gi.repository import Vte
except (ValueError, ImportError):
    Vte = None
from gi.repository import Adw, Gdk, GLib, Gtk, Pango

ACTIONS = [
    ("Everyday", [
        ("Update MOX", "software-update-available-symbolic", "sudo mox sync now"),
        ("Fix a problem", "emblem-system-symbolic", "mox fix"),
        ("System health", "emblem-ok-symbolic", "mox health"),
        ("Internet speed", "network-transmit-receive-symbolic", "mox speed"),
        ("What apps work", "view-app-grid-symbolic", "mox apps"),
    ]),
    ("Folders", [
        ("List files here", "folder-symbolic", "ls -lh"),
        ("Go to Home", "user-home-symbolic", "cd ~"),
        ("Go to Downloads", "folder-download-symbolic", "cd ~/Downloads"),
        ("Disk space", "drive-harddisk-symbolic", "df -h /"),
    ]),
    ("Tools", [
        ("Add from GitHub", "list-add-symbolic", "mox tool add "),
        ("My tools", "applications-engineering-symbolic", "mox tool list"),
        ("Free APIs", "network-server-symbolic", "mox api free"),
    ]),
]
PALETTE = ["#1b1b22", "#ff6b81", "#5ee7a0", "#ffd166", "#6ea8fe", "#c792ea", "#5ee7ff", "#d7d7e0",
           "#55556a", "#ff8fa3", "#8bf0bd", "#ffe08a", "#94c2ff", "#dcb2f5", "#94f1ff", "#ffffff"]
CSS = """
.mox-side { background-color: alpha(@window_bg_color, 0.55); padding: 14px 10px; }
.mox-side button { padding: 8px 10px; border-radius: 12px; }
.mox-side-title { font-size: 11px; font-weight: 700; opacity: 0.55; margin: 12px 8px 4px 8px; }
.mox-ask { border-radius: 14px; padding: 4px 8px; margin: 10px; }
"""


def color(code):
    value = Gdk.RGBA()
    value.parse(code)
    return value


class Window(Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="MOX Terminal", default_width=1080, default_height=680)
        self.tabs = Adw.TabView(vexpand=True, hexpand=True)
        self.tabs.connect("close-page", self.closing)
        bar = Adw.TabBar(view=self.tabs, autohide=True)
        self.ask = Gtk.Entry(placeholder_text="Type what you want in plain words, like: why is my wifi slow", css_classes=["mox-ask"], primary_icon_name="dialog-question-symbolic")
        self.ask.connect("activate", self.ask_mox)
        main = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        main.append(bar)
        main.append(self.tabs)
        main.append(self.ask)
        body = Gtk.Box()
        body.append(self.sidebar())
        body.append(main)
        view = Adw.ToolbarView()
        header = Adw.HeaderBar()
        new = Gtk.Button(icon_name="tab-new-symbolic", tooltip_text="New tab")
        new.connect("clicked", lambda _b: self.add_tab())
        header.pack_start(new)
        view.add_top_bar(header)
        view.set_content(body)
        self.set_content(view)
        keys = Gtk.EventControllerKey(propagation_phase=Gtk.PropagationPhase.CAPTURE)
        keys.connect("key-pressed", self.key)
        self.add_controller(keys)
        self.add_tab()

    def sidebar(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, css_classes=["mox-side"], width_request=210)
        for title, items in ACTIONS:
            box.append(Gtk.Label(label=title.upper(), xalign=0, css_classes=["mox-side-title"]))
            for label, icon, command in items:
                row = Gtk.Box(spacing=10)
                row.append(Gtk.Image(icon_name=icon))
                row.append(Gtk.Label(label=label, xalign=0))
                button = Gtk.Button(child=row, css_classes=["flat"])
                button.connect("clicked", lambda _b, text=command: self.send(text))
                box.append(button)
        return Gtk.ScrolledWindow(child=box, hscrollbar_policy=Gtk.PolicyType.NEVER)

    def add_tab(self):
        term = Vte.Terminal(hexpand=True, vexpand=True)
        term.set_font(Pango.FontDescription("Monospace 12"))
        term.set_colors(color("#e8e8ef"), color("#101016"), [color(code) for code in PALETTE])
        term.set_scrollback_lines(20000)
        term.set_cursor_blink_mode(Vte.CursorBlinkMode.ON)
        term.set_cursor_shape(Vte.CursorShape.IBEAM)
        term.set_enable_fallback_scrolling(True)
        term.connect("child-exited", self.ended)
        term.connect("window-title-changed", self.titled)
        shell = os.environ.get("SHELL", "/bin/bash")
        term.spawn_async(Vte.PtyFlags.DEFAULT, os.getcwd() if os.getcwd() != "/" else os.path.expanduser("~"), [shell], None, GLib.SpawnFlags.DEFAULT, None, None, -1, None, None, None)
        page = self.tabs.append(term)
        page.set_title("Terminal")
        self.tabs.set_selected_page(page)
        term.grab_focus()
        return term

    def current(self):
        page = self.tabs.get_selected_page()
        return page.get_child() if page else self.add_tab()

    def send(self, text):
        term = self.current()
        term.feed_child((text if text.endswith(" ") else text + "\n").encode())
        term.grab_focus()

    def ask_mox(self, entry):
        text = entry.get_text().strip()
        if text:
            self.send("mox ai " + shlex.quote(text))
            entry.set_text("")

    def titled(self, term):
        page = self.tabs.get_page(term)
        title = term.get_termprop_string("xterm.title") if hasattr(term, "get_termprop_string") else None
        if page and title:
            page.set_title(title[0] if isinstance(title, tuple) else title)

    def ended(self, term, _status):
        page = self.tabs.get_page(term)
        if self.tabs.get_n_pages() <= 1:
            self.close()
        elif page:
            self.tabs.close_page(page)

    def closing(self, view, page):
        view.close_page_finish(page, True)
        return Gdk.EVENT_STOP

    def key(self, _controller, keyval, _code, state):
        wanted = Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.SHIFT_MASK
        if (state & wanted) != wanted:
            return False
        name = Gdk.keyval_name(keyval).lower()
        if name == "c":
            self.current().copy_clipboard_format(Vte.Format.TEXT)
        elif name == "v":
            self.current().paste_clipboard()
        elif name == "t":
            self.add_tab()
        else:
            return False
        return True


def main():
    if Vte is None:
        for tool in ("ptyxis", "gnome-terminal", "xterm"):
            if shutil.which(tool):
                os.execvp(tool, [tool])
        return 1
    app = Adw.Application(application_id="org.mox.Terminal")

    def activate(application):
        provider = Gtk.CssProvider()
        provider.load_from_string(CSS)
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        Window(application).present()
    app.connect("activate", activate)
    return app.run(sys.argv[:1])
