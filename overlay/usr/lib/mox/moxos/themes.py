"""MOX themes: one command changes the whole look."""
import subprocess
from pathlib import Path

GTK_CSS = Path.home() / ".config/gtk-4.0/gtk.css"
START = "/* >>> MOX theme >>> */"
END = "/* <<< MOX theme <<< */"
WALLS = "/usr/share/backgrounds/mox"

THEMES = {
    "glass": {"label": "Glass", "scheme": "prefer-dark", "accent": "slate", "wallpaper": "mox-living.xml", "dock": 0.22, "window": 0.74, "sigma": 40},
    "frost": {"label": "Frost", "scheme": "prefer-light", "accent": "blue", "wallpaper": "frost.jpg", "dock": 0.30, "window": 0.78, "sigma": 40},
    "midnight": {"label": "Midnight", "scheme": "prefer-dark", "accent": "purple", "wallpaper": "night.jpg", "dock": 0.16, "window": 0.68, "sigma": 50},
    "graphite": {"label": "Graphite", "scheme": "prefer-dark", "accent": "slate", "wallpaper": "graphite.jpg", "dock": 0.45, "window": 0.92, "sigma": 20},
    "ember": {"label": "Ember", "scheme": "prefer-dark", "accent": "orange", "wallpaper": "dusk.jpg", "dock": 0.20, "window": 0.72, "sigma": 40},
    "ocean": {"label": "Ocean", "scheme": "prefer-dark", "accent": "teal", "wallpaper": "day.jpg", "dock": 0.20, "window": 0.72, "sigma": 40},
    "rose": {"label": "Rose", "scheme": "prefer-dark", "accent": "pink", "wallpaper": "dawn.jpg", "dock": 0.20, "window": 0.72, "sigma": 40},
    "aurora": {"label": "Aurora", "scheme": "prefer-dark", "accent": "teal", "wallpaper": "aurora.jpg", "dock": 0.20, "window": 0.72, "sigma": 40},
    "cobalt": {"label": "Cobalt", "scheme": "prefer-dark", "accent": "blue", "wallpaper": "cobalt.jpg", "dock": 0.20, "window": 0.72, "sigma": 40},
    "nebula": {"label": "Nebula", "scheme": "prefer-dark", "accent": "purple", "wallpaper": "nebula.jpg", "dock": 0.18, "window": 0.72, "sigma": 40},
    "dune": {"label": "Dune", "scheme": "prefer-light", "accent": "orange", "wallpaper": "dune.jpg", "dock": 0.30, "window": 0.82, "sigma": 40},
    "paper": {"label": "Paper", "scheme": "prefer-light", "accent": "slate", "wallpaper": "paper.jpg", "dock": 0.55, "window": 1.0, "sigma": 0},
}


def app_css(opacity):
    """Translucent app windows. Fully opaque themes remove the override."""
    if opacity >= 1:
        return ""
    return (
        f"{START}\n"
        f"window.background, .sidebar-pane, .content-pane {{ background-color: alpha(@window_bg_color, {opacity}); }}\n"
        f"headerbar {{ background-color: alpha(@headerbar_bg_color, {opacity}); box-shadow: none; }}\n"
        f"{END}\n"
    )


def merge_css(current, block):
    if START in current and END in current:
        head = current[:current.index(START)]
        tail = current[current.index(END) + len(END):].lstrip("\n")
        current = head + tail
    return current.rstrip("\n") + ("\n" if current.strip() else "") + block


def commands(name):
    theme = THEMES[name]
    uri = f"file://{WALLS}/{theme['wallpaper']}"
    dock = "org.gnome.shell.extensions.dash-to-dock"
    return [
        ["gsettings", "set", "org.gnome.desktop.interface", "color-scheme", theme["scheme"]],
        ["gsettings", "set", "org.gnome.desktop.interface", "accent-color", theme["accent"]],
        ["gsettings", "set", "org.gnome.desktop.interface", "gtk-theme", "Yaru" if theme["scheme"] == "prefer-light" else "Yaru-dark"],
        ["gsettings", "set", "org.gnome.desktop.background", "picture-uri", uri],
        ["gsettings", "set", "org.gnome.desktop.background", "picture-uri-dark", uri],
        ["dconf", "write", "/org/gnome/shell/extensions/dash-to-dock/background-opacity", str(theme["dock"])],
        ["dconf", "write", "/org/gnome/shell/extensions/blur-my-shell/applications/blur", "true" if theme["sigma"] else "false"],
        ["dconf", "write", "/org/gnome/shell/extensions/blur-my-shell/applications/enable-all", "true" if theme["sigma"] else "false"],
        ["dconf", "write", "/org/gnome/shell/extensions/blur-my-shell/applications/sigma", str(theme["sigma"])],
        ["dconf", "write", "/org/gnome/shell/extensions/blur-my-shell/applications/opacity", str(int(theme["window"] * 255))],
    ]


def apply(name):
    if name not in THEMES:
        raise KeyError(name)
    for command in commands(name):
        subprocess.run(command, check=False, capture_output=True)
    GTK_CSS.parent.mkdir(parents=True, exist_ok=True)
    current = GTK_CSS.read_text() if GTK_CSS.exists() else ""
    GTK_CSS.write_text(merge_css(current, app_css(THEMES[name]["window"])))
