"""Google Drive and iCloud as drives in your files."""
import re
import subprocess
from pathlib import Path

from .common import have, run

DRIVES = Path.home() / "Drives"
REMOTES = {"google": ("Google Drive", "drive"), "icloud": ("iCloud Drive", "iclouddrive")}


class CloudError(Exception):
    pass


def rclone_version(text=None):
    text = run(["rclone", "version"]) if text is None else text
    match = re.search(r"rclone v?(\d+)\.(\d+)", text)
    return (int(match[1]), int(match[2])) if match else (0, 0)


def connected():
    return [name.rstrip(":") for name in run(["rclone", "listremotes"]).split()]


def add(service):
    if service not in REMOTES:
        raise CloudError("Choose google or icloud.")
    if not have("rclone") or (service == "icloud" and rclone_version() < (1, 69)):
        if subprocess.run(["mox", "get", "cloud"], check=False).returncode != 0:
            raise CloudError("Couldn't install the cloud tool. Check your internet and try again.")
    label, backend = REMOTES[service]
    command = ["rclone", "config", "create", service, backend]
    if service == "icloud":
        print("Sign in with your Apple ID, then enter the code Apple sends you.")
        print("iCloud needs 'Access iCloud Data on the Web' on and Advanced Data Protection off.")
        command.append("--all")
    if subprocess.run(command, check=False).returncode != 0:
        raise CloudError(f"{label} sign-in did not finish.")
    mount(service)
    return label


def mount(service):
    (DRIVES / REMOTES[service][0]).mkdir(parents=True, exist_ok=True)
    return subprocess.run(["systemctl", "--user", "enable", "--now", f"mox-cloud@{service}.service"], check=False).returncode


def remove(service):
    subprocess.run(["systemctl", "--user", "disable", "--now", f"mox-cloud@{service}.service"], check=False)
    return subprocess.run(["rclone", "config", "delete", service], check=False).returncode
