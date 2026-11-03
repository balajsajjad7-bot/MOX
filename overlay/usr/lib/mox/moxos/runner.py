"""MOX Runner: open any app file with the right compatibility layer."""
import argparse
import os
import subprocess
import sys
import time
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from . import ipa
from .common import confirm, have, notify, run

ELF = b"\x7fELF"
MACHO = {b"\xfe\xed\xfa\xce", b"\xfe\xed\xfa\xcf", b"\xce\xfa\xed\xfe", b"\xcf\xfa\xed\xfe"}
SUFFIXES = {
    ".exe": "windows", ".msi": "windows-msi", ".bat": "windows-script", ".cmd": "windows-script",
    ".apk": "android", ".xapk": "android", ".ipa": "iphone",
    ".dmg": "mac", ".pkg": "mac", ".app": "mac",
    ".deb": "deb", ".rpm": "rpm", ".appimage": "appimage", ".flatpak": "flatpak", ".flatpakref": "flatpak",
    ".snap": "snap", ".sh": "script", ".py": "python", ".jar": "java",
}


@dataclass
class Plan:
    kind: str
    label: str
    command: list = field(default_factory=list)
    missing: str = ""        # `mox get` module the user needs first
    problem: str = ""        # why this file can't run at all
    ask: str = ""            # question to confirm before running


def detect(path):
    path = Path(path)
    suffix = path.suffix.lower()
    if path.is_dir():
        return "mac" if suffix == ".app" else "unknown"
    try:
        with open(path, "rb") as handle:
            head = handle.read(4096)
            handle.seek(max(path.stat().st_size - 512, 0))
            tail = handle.read(512)
    except OSError:
        return "missing"
    if head[:2] == b"MZ":
        return "windows"
    if head[:4] == ELF:
        return "appimage" if head[8:11] == b"AI\x02" else "linux"
    if head[:4] in MACHO:
        return "mac"
    if head[:4] == b"\xca\xfe\xba\xbe" and suffix != ".class":
        return "mac"
    if head[:8] == b"!<arch>\n" and b"debian-binary" in head[:72]:
        return "deb"
    if head[:4] == b"\xed\xab\xee\xdb":
        return "rpm"
    if head[:4] == b"xar!" or tail[:4] == b"koly":
        return "mac"
    if head[:2] == b"PK":
        try:
            with zipfile.ZipFile(path) as archive:
                names = archive.namelist()
        except zipfile.BadZipFile:
            names = []
        if "AndroidManifest.xml" in names or any(n.endswith(".apk") for n in names):
            return "android"
        if any(n.startswith("Payload/") and ".app/" in n for n in names):
            return "iphone"
        if "META-INF/MANIFEST.MF" in names:
            return "java"
    if suffix in SUFFIXES:
        return SUFFIXES[suffix]
    if head[:2] == b"#!":
        return "script"
    return "unknown"


def plan(path):
    path = str(Path(path).resolve())
    kind = detect(path)
    name = Path(path).name

    if kind == "windows":
        return Plan(kind, "Windows app (Wine)", ["wine", path], "" if have("wine") else "windows")
    if kind == "windows-msi":
        return Plan(kind, "Windows installer (Wine)", ["wine", "msiexec", "/i", path], "" if have("wine") else "windows")
    if kind == "windows-script":
        return Plan(kind, "Windows script (Wine)", ["wine", "cmd", "/c", path], "" if have("wine") else "windows")
    if kind == "android":
        return Plan(kind, "Android app (Waydroid)", ["waydroid", "app", "install", path], "" if have("waydroid") else "android")
    if kind == "iphone":
        report = ipa.inspect(path)
        if not report.supported:
            return Plan(kind, f"iPhone app: {report.name}", problem=report.reason + " Try the Android version of this app instead.")
        return Plan(kind, f"iPhone app (touchHLE): {report.name}", ["touchHLE", path], "" if have("touchHLE") else "iphone")
    if kind == "mac":
        return Plan(kind, "Mac app (Darling)", ["darling", "shell", path], "" if have("darling") else "mac")
    if kind == "linux":
        return Plan(kind, "Linux program", [path], ask=f"Run the program {name}?")
    if kind == "appimage":
        return Plan(kind, "Linux AppImage", [path], ask=f"Run the AppImage {name}?")
    if kind == "deb":
        return Plan(kind, "Debian/Ubuntu package", ["pkexec", "apt-get", "install", "-y", path], ask=f"Install {name}?")
    if kind == "rpm":
        return Plan(kind, "RPM package", ["pkexec", "alien", "-i", path], ask=f"Convert and install {name}?")
    if kind == "flatpak":
        return Plan(kind, "Flatpak", ["flatpak", "install", "-y", path], ask=f"Install {name}?")
    if kind == "snap":
        return Plan(kind, "Snap package", problem="MOX does not ship Snap. Look for a Flatpak, AppImage or .deb of this app.")
    if kind == "script":
        return Plan(kind, "Shell script", ["bash", path], ask=f"Run the script {name}?")
    if kind == "python":
        return Plan(kind, "Python script", ["python3", path], ask=f"Run the Python script {name}?")
    if kind == "java":
        return Plan(kind, "Java app", ["java", "-jar", path], ask=f"Run the Java app {name}?")
    if kind == "missing":
        return Plan(kind, "Missing file", problem=f"{path} could not be opened.")
    return Plan(kind, "Unknown file", problem=f"MOX doesn't recognise {name}.")


def start_android():
    """Start the Android container and wait until it accepts apps."""
    if "RUNNING" in run(["waydroid", "status"]).upper().split("CONTAINER")[-1][:40]:
        return True
    subprocess.Popen(["waydroid", "session", "start"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(45):
        time.sleep(2)
        if "RUNNING" in run(["waydroid", "status"]).upper():
            return True
    return False


def execute(item):
    if item.problem:
        notify("MOX can't open this file", item.problem)
        return 2
    if item.missing:
        if not confirm(f"{item.label} needs the '{item.missing}' add-on. Install it now?"):
            return 3
        if subprocess.run(["mox", "get", item.missing], check=False).returncode != 0:
            notify("Add-on failed", f"Run 'mox get {item.missing}' in Terminal to see the error.")
            return 3
    if item.ask and not confirm(item.ask):
        return 0
    if item.kind == "android" and not start_android():
        notify("Android didn't start", "Run 'mox fix android' in Terminal, then open the file again.")
        return 1
    if item.kind in ("linux", "appimage"):
        path = Path(item.command[0])
        if not os.access(path, os.X_OK):
            path.chmod(path.stat().st_mode | 0o700)
    code = subprocess.run(item.command, check=False).returncode
    if item.kind == "android" and code == 0:
        notify("App installed", "Opening Android. Your new app is in its app list.")
        subprocess.Popen(["mox-android"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return code


def main():
    parser = argparse.ArgumentParser(prog="mox-run", description="Open any app file on MOX")
    parser.add_argument("file")
    parser.add_argument("--explain", action="store_true", help="show what would happen without running it")
    args = parser.parse_args()
    item = plan(args.file)
    if args.explain:
        print(f"Type:    {item.label}")
        if item.command:
            print("Command: " + " ".join(item.command))
        if item.missing:
            print(f"Needs:   mox get {item.missing}")
        if item.problem:
            print(f"Problem: {item.problem}")
        return 2 if item.problem else 0
    return execute(item)


if __name__ == "__main__":
    sys.exit(main())
