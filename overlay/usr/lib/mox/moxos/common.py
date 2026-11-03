"""Shared helpers for the MOX tools."""
import configparser
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(os.environ.get("MOX_ROOT", "/"))
CONF = ROOT / "etc/mox/mox.conf"
VERSION_FILE = ROOT / "usr/lib/mox/VERSION"
PUBKEY = ROOT / "usr/share/mox/keys/creator.pub"
USER_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "mox"


def config():
    parser = configparser.ConfigParser(interpolation=None)
    parser.optionxform = str
    parser.read(CONF)
    return parser


def version():
    try:
        return VERSION_FILE.read_text().strip()
    except OSError:
        return "0.0.0"


def have(cmd):
    return shutil.which(cmd) is not None


def run(cmd, timeout=30):
    """Run a command and return its stdout, or "" if it is missing or fails."""
    try:
        done = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return done.stdout if done.returncode == 0 else ""


def has_terminal():
    return sys.stdin.isatty() and sys.stdout.isatty()


def notify(title, body=""):
    """Tell the user something, in the terminal or on the desktop."""
    if has_terminal() or not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
        print(f"{title}\n{body}".strip())
    elif have("zenity"):
        subprocess.run(["zenity", "--info", "--title", title, "--text", body or title, "--width", "440"], check=False)
    else:
        subprocess.run(["notify-send", title, body], check=False)


def confirm(question):
    if has_terminal():
        return input(f"{question} [y/N] ").strip().lower() in ("y", "yes")
    if have("zenity") and (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        return subprocess.run(["zenity", "--question", "--text", question, "--width", "440"], check=False).returncode == 0
    return False


def write_private(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as handle:
        handle.write(text)
