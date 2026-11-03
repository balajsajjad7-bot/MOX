"""MOX Browser: everyday browsing, plus isolated Tor windows for .onion sites."""
import re
import shutil
import subprocess
import sys
import threading
from pathlib import Path
from urllib.parse import quote_plus, urlparse

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("WebKit", "6.0")
from gi.repository import Adw, Gio, GLib, Gtk, WebKit

TOR_PORT = 9155
HOME = "https://duckduckgo.com/"
TOR_HOME = "https://duckduckgo.com/"
DOMAIN = re.compile(r"^[^\s/]+\.[^\s/]+(/.*)?$")


def to_url(text):
    text = text.strip()
    if re.match(r"^[a-z][a-z0-9+.-]*://", text, re.I):
        return text
    if DOMAIN.match(text) or text.startswith("localhost"):
        return ("http://" if ".onion" in text.split("/")[0] else "https://") + text
    return "https://duckduckgo.com/?q=" + quote_plus(text)


def is_onion(url):
    host = urlparse(url).hostname or ""
    return host.endswith(".onion")


class Tor:
    """A private Tor process that only the browser's Tor windows use."""
    process = None
    ready = False

    @classmethod
    def start(cls, on_status):
        if cls.ready:
            GLib.idle_add(on_status, 100, "")
            return
        if cls.process is None:
            folder = Path.home() / ".cache/mox/tor"
            folder.mkdir(parents=True, exist_ok=True, mode=0o700)
            cls.process = subprocess.Popen(
                ["tor", "--SocksPort", f"127.0.0.1:{TOR_PORT}", "--DataDirectory", str(folder), "--Log", "notice stdout"],
                stdout=subprocess.PIPE, text=True,
            )
            threading.Thread(target=cls._read, args=(on_status,), daemon=True).start()

    @classmethod
    def _read(cls, on_status):
        for line in cls.process.stdout:
            match = re.search(r"Bootstrapped (\d+)%[^:]*: (.*)", line)
            if match:
                percent = int(match[1])
                cls.ready = percent == 100
                GLib.idle_add(on_status, percent, match[2].strip())
        cls.ready = False

    @classmethod
    def stop(cls):
        if cls.process:
            cls.process.terminate()


class Browser(Adw.ApplicationWindow):
    def __init__(self, app, tor=False, url=None):
        super().__init__(application=app, title="MOX Browser", default_width=1240, default_height=800)
        self.tor = tor
        self.javascript = not tor
        if tor:
            self.session = WebKit.NetworkSession.new_ephemeral()
            settings = WebKit.NetworkProxySettings.new(f"socks5://127.0.0.1:{TOR_PORT}", None)
            self.session.set_proxy_settings(WebKit.NetworkProxyMode.CUSTOM, settings)
            self.add_css_class("mox-tor")
        else:
            data = Path.home() / ".local/share/mox/browser"
            cache = Path.home() / ".cache/mox/browser"
            self.session = WebKit.NetworkSession.new(str(data), str(cache))

        self.tabs = Adw.TabView()
        self.tabs.connect("notify::selected-page", lambda *_: self.sync())
        self.tabs.connect("close-page", self.on_close_page)
        bar = Adw.TabBar(view=self.tabs)
        self.address = Gtk.Entry(hexpand=True, placeholder_text="Search or enter an address")
        self.address.connect("activate", self.on_go)

        header = Adw.HeaderBar(title_widget=self.address)
        for icon, tip, action in (
            ("go-previous-symbolic", "Back", lambda _b: self.view() and self.view().go_back()),
            ("go-next-symbolic", "Forward", lambda _b: self.view() and self.view().go_forward()),
            ("view-refresh-symbolic", "Reload", lambda _b: self.view() and self.view().reload()),
        ):
            button = Gtk.Button(icon_name=icon, tooltip_text=tip)
            button.connect("clicked", action)
            header.pack_start(button)
        new = Gtk.Button(icon_name="tab-new-symbolic", tooltip_text="New tab")
        new.connect("clicked", lambda _b: self.open_tab(TOR_HOME if tor else HOME))
        header.pack_end(new)
        if tor:
            js = Gtk.ToggleButton(icon_name="applications-engineering-symbolic", tooltip_text="Allow JavaScript in new pages (less private)")
            js.connect("toggled", self.on_javascript)
            header.pack_end(js)
            real = Gtk.Button(label="Tor Browser", tooltip_text="The strongest anonymity")
            real.connect("clicked", lambda _b: subprocess.Popen(["torbrowser-launcher"]))
            header.pack_end(real)
        else:
            onion = Gtk.Button(label="Tor", tooltip_text="Open a private Tor window for .onion sites")
            onion.connect("clicked", lambda _b: Browser(self.get_application(), tor=True).present())
            header.pack_end(onion)

        self.banner = Adw.Banner(title="Connecting to Tor…", revealed=tor)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.append(self.banner)
        box.append(bar)
        box.append(self.tabs)
        toolbar = Adw.ToolbarView()
        toolbar.add_top_bar(header)
        toolbar.set_content(box)
        self.set_content(toolbar)

        if tor:
            self.pending = url or TOR_HOME
            self.set_title("MOX Browser - Tor")
            Tor.start(self.on_tor)
        else:
            self.open_tab(url or HOME)

    def on_tor(self, percent, text):
        if percent >= 100:
            self.banner.set_title("Connected through Tor. History isn't saved, and JavaScript is off.")
            if self.pending:
                self.open_tab(self.pending)
                self.pending = None
        else:
            self.banner.set_title(f"Connecting to Tor: {percent}% {text}")
        return False

    def make_view(self):
        view = WebKit.WebView(network_session=self.session)
        settings = view.get_settings()
        settings.set_enable_javascript(self.javascript)
        settings.set_enable_webrtc(False)
        settings.set_enable_developer_extras(not self.tor)
        if self.tor:
            settings.set_user_agent("Mozilla/5.0 (Windows NT 10.0; rv:128.0) Gecko/20100101 Firefox/128.0")
            settings.set_enable_media_stream(False)
            settings.set_enable_webgl(False)
        view.connect("notify::uri", lambda *_: self.sync())
        view.connect("notify::title", self.on_title)
        view.connect("decide-policy", self.on_policy)
        view.connect("create", lambda _v, _a: self.open_tab(None))
        return view

    def open_tab(self, url):
        view = self.make_view()
        page = self.tabs.append(view)
        page.set_title("New tab")
        self.tabs.set_selected_page(page)
        if url:
            view.load_uri(url)
        return view

    def view(self):
        page = self.tabs.get_selected_page()
        return page.get_child() if page else None

    def sync(self):
        view = self.view()
        if view:
            self.address.set_text(view.get_uri() or "")

    def on_title(self, view, _param):
        page = self.tabs.get_page(view)
        if page:
            page.set_title(view.get_title() or "New tab")

    def on_go(self, entry):
        url = to_url(entry.get_text())
        if is_onion(url) and not self.tor:
            Browser(self.get_application(), tor=True, url=url).present()
            return
        view = self.view() or self.open_tab(None)
        view.load_uri(url)

    def on_policy(self, _view, decision, kind):
        if kind == WebKit.PolicyDecisionType.NAVIGATION_ACTION and not self.tor:
            uri = decision.get_navigation_action().get_request().get_uri()
            if is_onion(uri):
                decision.ignore()
                Browser(self.get_application(), tor=True, url=uri).present()
                return True
        return False

    def on_javascript(self, button):
        self.javascript = button.get_active()
        view = self.view()
        if view:
            view.get_settings().set_enable_javascript(self.javascript)
            view.reload()

    def on_close_page(self, tabs, page):
        tabs.close_page_finish(page, True)
        if tabs.get_n_pages() == 0:
            self.close()
        return True


def on_activate(app):
    (app.get_active_window() or Browser(app)).present()


def on_open(app, files, _count, _hint):
    for item in files:
        url = item.get_uri()
        Browser(app, tor=is_onion(url), url=url).present()


def main():
    if shutil.which("tor") is None:
        print("Tor isn't installed. Run: sudo apt install tor", file=sys.stderr)
    app = Adw.Application(application_id="org.mox.Browser", flags=Gio.ApplicationFlags.HANDLES_OPEN)
    app.connect("activate", on_activate)
    app.connect("open", on_open)
    code = app.run(sys.argv)
    Tor.stop()
    return code
