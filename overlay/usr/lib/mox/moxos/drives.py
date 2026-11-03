"""Lists disks for This PC."""
import json

from .common import run


def human(size):
    size = float(size or 0)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024:
            return f"{size:.0f} {unit}" if unit in ("B", "KB") else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} PB"


def flatten(devices, disk=None):
    for device in devices:
        top = disk or device
        yield device, top
        yield from flatten(device.get("children") or [], top)


def parse(text):
    """Turn `lsblk -J -b` output into drives a person cares about."""
    drives = []
    for device, disk in flatten(json.loads(text).get("blockdevices", [])):
        if device.get("type") not in ("part", "crypt", "lvm") or not device.get("fstype"):
            continue
        if device["fstype"] in ("swap", "crypto_LUKS", "LVM2_member", "squashfs"):
            continue
        mountpoint = device.get("mountpoint")
        if mountpoint and mountpoint.startswith(("/boot", "/cdrom", "/rofs", "/snap")):
            continue
        size = int(device.get("size") or 0)
        used = int(device.get("fsused") or 0)
        name = device.get("label") or ("This PC" if mountpoint == "/" else human(size) + " drive")
        drives.append({
            "name": name,
            "device": device.get("path") or "/dev/" + device["name"],
            "mountpoint": mountpoint,
            "size": size,
            "used": used,
            "fraction": used / size if size else 0.0,
            "text": f"{human(int(device.get('fsavail') or 0))} free of {human(size)}" if mountpoint else f"{human(size)}, not opened yet",
            "removable": bool(disk.get("rm") or disk.get("hotplug")),
        })
    return drives


def list_drives():
    return parse(run(["lsblk", "-J", "-b", "-o", "NAME,PATH,TYPE,FSTYPE,LABEL,SIZE,FSAVAIL,FSUSED,MOUNTPOINT,RM,HOTPLUG"]) or "{}")
