"""MOX Control: the desktop home for hardware, AI, tools and updates."""
import shutil
import subprocess
import sys
import threading
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk

from . import addons, adblock, ai, connectors, hardware, health, shield, wifi, fixer, display, themes, update, vault, vpn, wallpaper
from .cli import LAYERS, TOOLS
from .common import USER_DIR, version

CSS = """
.mox-hero { background: linear-gradient(120deg, #1b1f4b, #4b2a8c 45%, #c2477a 80%, #f08a5d); border-radius: 22px; padding: 30px; color: white; }
.mox-hero-title { font-size: 34px; font-weight: 800; letter-spacing: -1px; }
.mox-pulse { animation: mox-pulse 3.2s ease-in-out infinite; }
@keyframes mox-pulse { 0% { opacity: .78; } 50% { opacity: 1; } 100% { opacity: .78; } }
.mox-stat { background: alpha(@card_bg_color, .72); border-radius: 16px; padding: 16px; }
.mox-stat-value { font-size: 17px; font-weight: 700; }
.mox-output { font-family: "JetBrains Mono", monospace; font-size: 12.5px; }
"""
PAGES = [
    ("home", "Overview", "computer-symbolic"),
    ("fix", "Troubleshooter", "dialog-question-symbolic"),
    ("power", "Display & Power", "video-display-symbolic"),
    ("apps", "App Support", "application-x-executable-symbolic"),
    ("hardware", "Hardware & Drivers", "preferences-system-symbolic"),
    ("health", "Health & Optimizer", "emblem-ok-symbolic"),
    ("ai", "MOX AI", "dialog-information-symbolic"),
    ("dev", "Developer Tools", "utilities-terminal-symbolic"),
    ("security", "Security Tools", "security-high-symbolic"),
    ("shield", "Shield", "security-medium-symbolic"),
    ("wifi", "WiFi Tools", "network-wireless-symbolic"),
    ("vpn", "MOXWALL VPN", "network-vpn-symbolic"),
    ("vault", "API Vault", "dialog-password-symbolic"),
    ("connect", "Connectors", "network-workgroup-symbolic"),
    ("look", "Appearance", "preferences-desktop-appearance-symbolic"),
    ("updates", "Updates", "software-update-available-symbolic"),
]


def terminal(command):
    shell = f"{command}; echo; read -r -p 'Press Enter to close'"
    for tool in (["ptyxis", "--new-window", "--"], ["gnome-terminal", "--"]):
        if shutil.which(tool[0]):
            subprocess.Popen(tool + ["bash", "-c", shell])
            return


def background(work, done):
    def runner():
        try:
            result = work()
        except Exception as error:  # shown to the user on the page
            result = error
        GLib.idle_add(done, result)
    threading.Thread(target=runner, daemon=True).start()


def page(title, subtitle=""):
    prefs = Adw.PreferencesPage(title=title)
    group = Adw.PreferencesGroup(title=title, description=subtitle)
    prefs.add(group)
    return prefs, group


def stat(label, value):
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4, hexpand=True, css_classes=["mox-stat"])
    box.append(Gtk.Label(label=label, xalign=0, css_classes=["dim-label", "caption"]))
    text = Gtk.Label(label=value, xalign=0, wrap=True, css_classes=["mox-stat-value"])
    box.append(text)
    return box, text


class Control(Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="MOX Control", default_width=1040, default_height=720)
        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.SLIDE_UP_DOWN, transition_duration=240)
        sidebar = Gtk.ListBox(css_classes=["navigation-sidebar"])
        sidebar.connect("row-selected", self.on_select)
        for name, title, icon in PAGES:
            row = Gtk.ListBoxRow()
            row.page = name
            line = Gtk.Box(spacing=12, margin_top=8, margin_bottom=8, margin_start=8)
            line.append(Gtk.Image(icon_name=icon))
            line.append(Gtk.Label(label=title))
            row.set_child(line)
            sidebar.append(row)
            self.stack.add_titled(getattr(self, f"build_{name}")(), name, title)

        side = Adw.ToolbarView()
        side.add_top_bar(Adw.HeaderBar(show_title=False))
        side.set_content(Gtk.ScrolledWindow(child=sidebar, vexpand=True))
        main = Adw.ToolbarView()
        main.add_top_bar(Adw.HeaderBar())
        main.set_content(self.stack)
        split = Adw.NavigationSplitView()
        split.set_sidebar(Adw.NavigationPage(title="MOX", child=side))
        split.set_content(Adw.NavigationPage(title="MOX Control", child=main))
        self.set_content(split)
        sidebar.select_row(sidebar.get_row_at_index(0))

    def on_select(self, _box, row):
        if row:
            self.stack.set_visible_child_name(row.page)

    def build_home(self):
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16, margin_top=20, margin_bottom=20, margin_start=24, margin_end=24)
        hero = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, css_classes=["mox-hero"])
        hero.append(Gtk.Label(label="MOX", xalign=0, css_classes=["mox-hero-title", "mox-pulse"]))
        hero.append(Gtk.Label(label=f"Version {version()}. The father of Modo.", xalign=0))
        outer.append(hero)
        grid = Gtk.Grid(row_spacing=12, column_spacing=12, column_homogeneous=True)
        cards = {}
        for index, (key, label) in enumerate([("cpu", "Processor"), ("memory", "Memory"), ("kernel", "Kernel"), ("drivers", "Drivers")]):
            box, text = stat(label, "Checking…")
            cards[key] = text
            grid.attach(box, index % 2, index // 2, 1, 1)
        outer.append(grid)
        live = Path("/proc/cmdline").read_text().find("boot=casper") >= 0 if Path("/proc/cmdline").exists() else False
        if live:
            button = Gtk.Button(label="Install MOX on this computer", css_classes=["suggested-action", "pill"], halign=Gtk.Align.START)
            button.connect("clicked", lambda _b: subprocess.Popen(["mox-install"]))
            outer.append(button)

        def show(data):
            if isinstance(data, Exception):
                return
            cards["cpu"].set_label(f"{data['cpu'] or 'Unknown'} ({data['cores']} threads)")
            cards["memory"].set_label(f"{data['memory_gb']} GB")
            cards["kernel"].set_label(data["kernel"])
            missing = len(data["missing_drivers"])
            extra = len(data["available_drivers"])
            cards["drivers"].set_label(f"{missing} missing, {extra} available" if missing or extra else "All set")

        background(hardware.summary, show)
        return Gtk.ScrolledWindow(child=outer)

    def build_fix(self):
        prefs, group = page("Troubleshooter", "MOX tries safe fixes on its own. If they don't work, MOX AI suggests more, and you approve each command.")
        for name, problem in fixer.PROBLEMS.items():
            row = Adw.ActionRow(title=problem["label"])
            button = Gtk.Button(label="Fix it", valign=Gtk.Align.CENTER, css_classes=["suggested-action"])
            button.connect("clicked", lambda _b, item=name: terminal(f"mox fix {item}"))
            row.add_suffix(button)
            group.add(row)
        return prefs

    def build_power(self):
        prefs, group = page("Displays", "Duplicate, extend, external only or built-in only. Shortcut: Super+P.")
        row = Adw.ActionRow(title="Switch display mode")
        button = Gtk.Button(label="Choose", valign=Gtk.Align.CENTER)
        button.connect("clicked", lambda _b: display.switch_displays())
        row.add_suffix(button)
        group.add(row)
        more = Adw.ActionRow(title="Resolution, scale and arrangement")
        open_settings = Gtk.Button(label="Open", valign=Gtk.Align.CENTER)
        open_settings.connect("clicked", lambda _b: subprocess.Popen(["gnome-control-center", "display"]))
        more.add_suffix(open_settings)
        group.add(more)
        plans = Adw.PreferencesGroup(title="Power plan", description="Sets screen-off time, sleep time and processor speed together.")
        prefs.add(plans)
        for key, label, info in (("saver", "Battery Saver", "Screen off after 2 minutes"), ("balanced", "Balanced", "Screen off after 5 minutes"), ("performance", "Performance", "Never sleeps on power")):
            row = Adw.ActionRow(title=label, subtitle=info)
            apply = Gtk.Button(label="Use", valign=Gtk.Align.CENTER)
            apply.connect("clicked", lambda _b, item=key: display.apply_plan(item))
            row.add_suffix(apply)
            plans.add(row)
        actions = Adw.PreferencesGroup(title="Power")
        prefs.add(actions)
        row = Adw.ActionRow(title="Power menu", subtitle="Lock, sleep, restart, shut down. Shortcut: Ctrl+Alt+Delete")
        menu = Gtk.Button(label="Open", valign=Gtk.Align.CENTER)
        menu.connect("clicked", lambda _b: subprocess.Popen(["mox-power"]))
        row.add_suffix(menu)
        actions.add(row)
        return prefs

    def build_apps(self):
        prefs, group = page("App Support", "Double-click any app file and MOX Runner picks the right layer.")
        for label, binary, addon in LAYERS:
            ready = binary is None or addons.is_installed(addon)
            row = Adw.ActionRow(title=label, subtitle="Ready" if ready else "Add-on not installed yet")
            if not ready:
                button = Gtk.Button(label="Install", valign=Gtk.Align.CENTER)
                button.connect("clicked", lambda _b, name=addon: terminal(f"mox get {name}"))
                row.add_suffix(button)
            group.add(row)
        extras = Adw.PreferencesGroup(title="Add-ons")
        prefs.add(extras)
        for name, (label, _script) in addons.ADDONS.items():
            installed = addons.is_installed(name)
            row = Adw.ActionRow(title=label, subtitle="Installed" if installed else f"mox get {name}")
            if installed:
                row.add_suffix(Gtk.Image(icon_name="object-select-symbolic", valign=Gtk.Align.CENTER))
            else:
                button = Gtk.Button(label="Install", valign=Gtk.Align.CENTER)
                button.connect("clicked", lambda _b, item=name: terminal(f"mox get {item}"))
                row.add_suffix(button)
            extras.add(row)
        return prefs

    def build_hardware(self):
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, margin_top=20, margin_bottom=20, margin_start=24, margin_end=24)
        actions = Gtk.Box(spacing=10)
        install = Gtk.Button(label="Install recommended drivers", css_classes=["suggested-action"])
        install.connect("clicked", lambda _b: terminal("mox drivers --install"))
        ask = Gtk.Button(label="Ask AI about missing drivers")
        ask.connect("clicked", lambda _b: terminal("mox drivers --ai"))
        monitor = Gtk.Button(label="Live monitor")
        monitor.connect("clicked", lambda _b: terminal("btop"))
        for widget in (install, ask, monitor):
            actions.append(widget)
        outer.append(actions)
        view = Gtk.Label(label="Scanning hardware…", xalign=0, yalign=0, wrap=True, selectable=True, css_classes=["mox-output"])
        outer.append(Gtk.ScrolledWindow(child=view, vexpand=True))
        background(lambda: hardware.text_report(hardware.summary()), lambda text: view.set_label(str(text)))
        return outer

    def build_health(self):
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, margin_top=20, margin_bottom=20, margin_start=24, margin_end=24)
        tune = Gtk.Button(label="Optimize for this PC", css_classes=["suggested-action"], halign=Gtk.Align.START)
        tune.connect("clicked", lambda _b: terminal("mox optimize"))
        outer.append(tune)
        view = Gtk.Label(label="Checking health…", xalign=0, yalign=0, wrap=True, selectable=True, css_classes=["mox-output"])
        outer.append(Gtk.ScrolledWindow(child=view, vexpand=True))
        background(lambda: health.text(health.report()), lambda text: view.set_label(str(text)))
        return outer

    def build_ai(self):
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, margin_top=20, margin_bottom=20, margin_start=24, margin_end=24)
        state = ai.status()
        names = [name for name, on in (("Claude key", state["claude_key"]), ("OpenAI key", state["openai_key"]), ("Ollama", state["ollama_running"]), ("Claude Code", state["claude_code"]), ("Codex", state["codex"]), ("llama.cpp", state["llama_cpp"])) if on]
        outer.append(Gtk.Label(label="Ready: " + (", ".join(names) or "nothing yet. Add a key to start."), xalign=0, css_classes=["dim-label"]))
        keys = Gtk.Box(spacing=10)
        for provider, label in (("anthropic", "Add Claude key"), ("openai", "Add OpenAI key")):
            button = Gtk.Button(label=label)
            button.connect("clicked", lambda _b, item=provider: terminal(f"mox ai key {item}"))
            keys.append(button)
        chat = Gtk.Button(label="Open MOX Bot")
        chat.connect("clicked", lambda _b: subprocess.Popen(["mox-bot"]))
        keys.append(chat)
        code = Gtk.Button(label="Open Claude Code")
        code.connect("clicked", lambda _b: terminal("claude"))
        keys.append(code)
        outer.append(keys)
        reply = Gtk.Label(label="Ask anything about this computer or your code.", xalign=0, yalign=0, wrap=True, selectable=True)
        outer.append(Gtk.ScrolledWindow(child=reply, vexpand=True))
        entry = Gtk.Entry(placeholder_text="Ask MOX AI", hexpand=True)

        def send(widget):
            text = widget.get_text().strip()
            if not text:
                return
            widget.set_text("")
            reply.set_label("Thinking…")
            background(lambda: ai.ask(text), lambda answer: reply.set_label(str(answer)))

        entry.connect("activate", send)
        outer.append(entry)
        return outer

    def build_dev(self):
        prefs, group = page("Developer Tools", "Installed and ready in every terminal.")
        prefs.remove(group)
        for title in ("Languages", "Build", "AI"):
            section = Adw.PreferencesGroup(title=title)
            prefs.add(section)
            for tool in TOOLS[title]:
                section.add(Adw.ActionRow(title=tool, subtitle=(shutil.which(tool) or "Not installed")))
        return prefs

    def build_security(self):
        prefs, group = page("Security Tools", "Use these only on systems you own or have written permission to test.")
        for tool in TOOLS["Security"]:
            found = shutil.which(tool)
            row = Adw.ActionRow(title=tool, subtitle=found or "Not installed")
            if found:
                button = Gtk.Button(label="Open", valign=Gtk.Align.CENTER)
                button.connect("clicked", lambda _b, item=tool: terminal(f"{item} --help | less"))
                row.add_suffix(button)
            group.add(row)
        return prefs

    def build_connect(self):
        prefs, group = page("Connectors", f"MCP servers shared by your AI tools. Saved in {USER_DIR / 'mcp.json'}.")
        name = Adw.EntryRow(title="Name")
        target = Adw.EntryRow(title="URL or command")
        group.add(name)
        group.add(target)
        add = Gtk.Button(label="Add connector", css_classes=["suggested-action"], halign=Gtk.Align.START, margin_top=10)
        group.add(add)
        current = Adw.PreferencesGroup(title="Connected")
        prefs.add(current)
        rows = []

        def refresh():
            for row in rows:
                current.remove(row)
            rows.clear()
            for key, entry in connectors.load()["mcpServers"].items():
                row = Adw.ActionRow(title=key, subtitle=entry.get("url") or entry.get("command", ""))
                remove = Gtk.Button(icon_name="user-trash-symbolic", valign=Gtk.Align.CENTER, css_classes=["flat"])
                remove.connect("clicked", lambda _b, item=key: (connectors.remove(item), refresh()))
                row.add_suffix(remove)
                current.add(row)
                rows.append(row)

        def on_add(_button):
            if name.get_text().strip() and target.get_text().strip():
                connectors.add(name.get_text().strip(), target.get_text().strip())
                name.set_text("")
                target.set_text("")
                refresh()

        add.connect("clicked", on_add)
        refresh()
        return prefs

    def build_shield(self):
        prefs, group = page("MOX Shield", "Firewall, ClamAV antivirus and rootkit checks.")
        names = {"firewall": "Firewall", "antivirus": "Antivirus", "virus_signatures": "Virus signatures", "rootkit_checks": "Rootkit checks", "blocked_today": "Blocked today"}
        rows = {key: Adw.ActionRow(title=title, subtitle="Checking…") for key, title in names.items()}
        for row in rows.values():
            group.add(row)
        background(shield.status, lambda data: [rows[key].set_subtitle(str(value)) for key, value in data.items()] if isinstance(data, dict) else None)
        actions = Adw.PreferencesGroup(title="Actions")
        prefs.add(actions)
        blocked = Adw.ActionRow(title="Ad block", subtitle=f"{adblock.blocked_count()} ad and tracker domains blocked")
        group.add(blocked)
        for title, command in (("Scan my files", "mox shield scan"), ("Update virus signatures", "mox shield update"), ("Check for rootkits", "mox shield rootkit"), ("Refresh ad block list", "sudo mox adblock on"), ("Turn ad block off", "sudo mox adblock off")):
            row = Adw.ActionRow(title=title, subtitle=command)
            button = Gtk.Button(label="Run", valign=Gtk.Align.CENTER)
            button.connect("clicked", lambda _b, item=command: terminal(item))
            row.add_suffix(button)
            actions.add(row)
        return prefs

    def build_wifi(self):
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, margin_top=20, margin_bottom=20, margin_start=24, margin_end=24)
        actions = Gtk.Box(spacing=10)
        for label, command in (("Test latency", "mox wifi ping"), ("Speed test", "mox speed"), ("Share WiFi with QR", "mox wifi qr \"$(nmcli -t -f NAME connection show --active | head -1)\""), ("Live signal", "wavemon")):
            button = Gtk.Button(label=label)
            button.connect("clicked", lambda _b, item=command: terminal(item))
            actions.append(button)
        outer.append(actions)
        view = Gtk.Label(label="Scanning nearby networks…", xalign=0, yalign=0, wrap=True, selectable=True, css_classes=["mox-output"])
        outer.append(Gtk.ScrolledWindow(child=view, vexpand=True))

        def report():
            networks = wifi.scan()
            lines = [f"{'●' if n['active'] else ' '} {n['ssid'][:26]:26} {n['signal']:3}%  ch {n['channel']:<3} {n['band']:7} {n['security']}" for n in sorted(networks, key=lambda n: -n['signal'])]
            return "\n".join(lines + ["", *wifi.advice(networks)]) if networks else "No WiFi adapter or networks found."

        background(report, lambda text: view.set_label(str(text)))
        return outer

    def build_vpn(self):
        prefs, group = page("MOXWALL VPN", "WireGuard tunnels. A VPN needs a server: use your provider's config, or create your own.")
        items = vpn.tunnels()
        for item in items:
            row = Adw.ActionRow(title=item["name"], subtitle="Connected" if item["active"] else "Off")
            button = Gtk.Button(label="Disconnect" if item["active"] else "Connect", valign=Gtk.Align.CENTER)
            button.connect("clicked", lambda _b, name=item["name"], on=item["active"]: vpn.switch(name, not on))
            row.add_suffix(button)
            group.add(row)
        if not items:
            group.add(Adw.ActionRow(title="No tunnels yet", subtitle="mox vpn import FILE.conf, or mox vpn make-server YOUR_SERVER_IP"))
        return prefs

    def build_vault(self):
        prefs, group = page("API Vault", "Every key in one private place, loaded into each new terminal.")
        name = Adw.EntryRow(title="Name, like OPENAI_API_KEY")
        secret = Adw.PasswordEntryRow(title="Key")
        group.add(name)
        group.add(secret)
        save = Gtk.Button(label="Save key", css_classes=["suggested-action"], halign=Gtk.Align.START, margin_top=10)
        group.add(save)
        saved = Adw.PreferencesGroup(title="Saved keys")
        prefs.add(saved)
        rows = []

        def refresh():
            for row in rows:
                saved.remove(row)
            rows.clear()
            for key, value in vault.masked().items():
                row = Adw.ActionRow(title=key, subtitle=value)
                remove = Gtk.Button(icon_name="user-trash-symbolic", valign=Gtk.Align.CENTER, css_classes=["flat"])
                remove.connect("clicked", lambda _b, item=key: (vault.remove(item), refresh()))
                row.add_suffix(remove)
                saved.add(row)
                rows.append(row)

        def on_save(_button):
            try:
                vault.add(name.get_text().strip(), secret.get_text().strip())
            except ValueError as error:
                name.set_title(str(error))
                return
            name.set_text("")
            secret.set_text("")
            refresh()

        save.connect("clicked", on_save)
        refresh()
        return prefs

    def build_look(self):
        prefs, gallery = page("Themes", "Each theme changes colors, glass, dock and wallpaper together.")
        for key, theme in themes.THEMES.items():
            row = Adw.ActionRow(title=theme["label"], subtitle=f"{'Light' if theme['scheme'] == 'prefer-light' else 'Dark'}, {theme['accent']} accent")
            button = Gtk.Button(label="Apply", valign=Gtk.Align.CENTER)
            button.connect("clicked", lambda _b, item=key: themes.apply(item))
            row.add_suffix(button)
            gallery.add(row)
        group = Adw.PreferencesGroup(title="Wallpapers", description="Trending images use your own TMDB or RAWG key and stay on this computer.")
        prefs.add(group)
        for title, kind in (("MOX Living", "living"), ("Trending movie", "movie"), ("Trending series", "tv"), ("Popular game", "game")):
            row = Adw.ActionRow(title=title, subtitle=f"mox wallpaper {kind}")
            button = Gtk.Button(label="Use", valign=Gtk.Align.CENTER)
            button.connect("clicked", lambda _b, item=kind: terminal(f"mox wallpaper {item}"))
            row.add_suffix(button)
            group.add(row)
        return prefs

    def build_updates(self):
        prefs, group = page("Updates", "MOX only accepts releases signed by its creator.")
        row = Adw.ActionRow(title=f"Installed version {version()}", subtitle="Not checked yet")
        check = Gtk.Button(label="Check now", valign=Gtk.Align.CENTER)
        install = Gtk.Button(label="Install", valign=Gtk.Align.CENTER, visible=False, css_classes=["suggested-action"])
        install.connect("clicked", lambda _b: terminal("sudo mox update"))

        def done(result):
            if isinstance(result, Exception):
                row.set_subtitle(str(result))
            elif result:
                row.set_subtitle(f"MOX {result['version']} is ready")
                install.set_visible(True)
            else:
                row.set_subtitle("MOX is up to date")

        check.connect("clicked", lambda _b: background(update.check, done))
        row.add_suffix(check)
        row.add_suffix(install)
        group.add(row)
        return prefs


def on_activate(app):
    provider = Gtk.CssProvider()
    provider.load_from_string(CSS)
    Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
    window = app.get_active_window() or Control(app)
    window.present()


def main():
    app = Adw.Application(application_id="org.mox.Control", flags=Gio.ApplicationFlags.DEFAULT_FLAGS)
    Adw.StyleManager.get_default().set_color_scheme(Adw.ColorScheme.PREFER_DARK)
    app.connect("activate", on_activate)
    return app.run(sys.argv[:1])
