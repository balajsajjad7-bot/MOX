"""MOX Wipe: permanent erase of files and whole drives."""
import json
import os
import subprocess
from pathlib import Path

from .common import confirm, run


class WipeError(Exception):
    pass


def disk_kind(name):
    if name.startswith("nvme"):
        return "nvme"
    try:
        return "hdd" if (Path("/sys/block") / name / "queue/rotational").read_text().strip() == "1" else "ssd"
    except OSError:
        raise WipeError(f"{name} isn't a disk here.") from None


def system_disks(text=None):
    """Names of disks holding the running system, which must never be erased."""
    data = json.loads(text if text is not None else run(["lsblk", "-J", "-o", "NAME,MOUNTPOINT,TYPE"]) or "{}")
    found = set()

    def walk(device):
        hit = device.get("mountpoint") in ("/", "/boot", "/boot/efi", "/usr", "/rofs", "/cdrom")
        for child in device.get("children") or []:
            hit = walk(child) or hit
        return hit

    for disk in data.get("blockdevices", []):
        if walk(disk):
            found.add(disk["name"])
    return found


def plan(name):
    """The strongest erase for this kind of disk. Commands are not run here."""
    device = f"/dev/{name}"
    return {
        "nvme": [["nvme", "format", device, "--ses=2", "--force"], ["blkdiscard", "-f", device]],
        "ssd": [["blkdiscard", "--secure", "-f", device], ["blkdiscard", "-f", device]],
        "hdd": [["shred", "-v", "-n", "1", "-z", device]],
    }[disk_kind(name)]


def erase_disk(name):
    if os.geteuid() != 0:
        raise WipeError("Erasing a drive needs administrator rights. Run: sudo mox wipe disk NAME")
    if name in system_disks():
        raise WipeError("That disk runs this system. To erase it, boot MOX from USB first.")
    if not confirm(f"Permanently erase ALL data on /dev/{name}? This can't be undone."):
        return 1
    for command in plan(name):
        if subprocess.run(command, check=False).returncode == 0:
            return 0
    raise WipeError("The disk refused every erase method.")


def erase_keys(name):
    """Destroy the encryption keys of a LUKS drive, making its data unreadable at once."""
    if os.geteuid() != 0:
        raise WipeError("This needs administrator rights.")
    device = f"/dev/{name}"
    if subprocess.run(["cryptsetup", "isLuks", device], check=False).returncode != 0:
        raise WipeError(f"{device} isn't an encrypted drive.")
    if not confirm(f"Destroy the keys on {device}? Everything on it becomes permanently unreadable."):
        return 1
    return subprocess.run(["cryptsetup", "erase", "-q", device], check=False).returncode


def shred_file(path):
    return subprocess.run(["shred", "-u", "-z", str(path)], check=False).returncode
