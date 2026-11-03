"""Hardware inventory and driver setup."""
import json
import os
import re
import subprocess
from pathlib import Path

from .common import have, run


def parse_lspci_k(text):
    """Turn `lspci -nnk` output into a device list."""
    devices = []
    for line in text.splitlines():
        if line and not line[0].isspace():
            match = re.match(r"(\S+)\s+(.*?):\s+(.*)$", line)
            if match:
                devices.append({"slot": match[1], "class": re.sub(r"\s*\[[0-9a-f]{4}\]$", "", match[2]), "name": match[3], "driver": ""})
        elif devices and "Kernel driver in use:" in line:
            devices[-1]["driver"] = line.split(":", 1)[1].strip()
    return devices


def parse_ubuntu_drivers(text):
    """Turn `ubuntu-drivers list --recommended`-style output into package names."""
    return [line.split(",")[0].strip() for line in text.splitlines() if re.match(r"^[a-z0-9][a-z0-9.+-]+(,|$)", line.strip())]


NEEDS_DRIVER = ("VGA", "3D", "Display", "Network", "Ethernet", "Wireless", "Audio", "Multimedia", "Bluetooth")


def summary():
    cpu = ""
    try:
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.startswith("model name"):
                cpu = line.split(":", 1)[1].strip()
                break
    except OSError:
        pass
    memory_gb = 0.0
    try:
        memory_gb = round(int(Path("/proc/meminfo").read_text().split()[1]) / 1048576, 1)
    except (OSError, ValueError, IndexError):
        pass
    devices = parse_lspci_k(run(["lspci", "-nnk"]))
    disks = run(["lsblk", "-dno", "NAME,SIZE,MODEL"]).strip().splitlines()
    return {
        "cpu": cpu,
        "cores": os.cpu_count(),
        "memory_gb": memory_gb,
        "kernel": os.uname().release,
        "disks": disks,
        "pci": devices,
        "usb": run(["lsusb"]).strip().splitlines(),
        "missing_drivers": [d for d in devices if not d["driver"] and any(k in d["class"] for k in NEEDS_DRIVER)],
        "available_drivers": parse_ubuntu_drivers(run(["ubuntu-drivers", "list"], timeout=60)) if have("ubuntu-drivers") else [],
    }


def text_report(data):
    lines = [f"CPU      {data['cpu']} ({data['cores']} threads)", f"Memory   {data['memory_gb']} GB", f"Kernel   {data['kernel']}"]
    lines += [f"Disk     {disk}" for disk in data["disks"]]
    for device in data["pci"]:
        if any(key in device["class"] for key in NEEDS_DRIVER):
            lines.append(f"{device['class'][:22]:22} {device['name']}  [{device['driver'] or 'NO DRIVER'}]")
    lines.append("Drivers to add: " + (", ".join(data["available_drivers"]) or "none"))
    lines.append("Without a driver: " + (", ".join(d["name"] for d in data["missing_drivers"]) or "none"))
    return "\n".join(lines)


def install_drivers():
    """Install the recommended drivers and firmware. Must run as root."""
    if os.geteuid() != 0:
        return subprocess.run(["pkexec", "mox", "drivers", "--install"], check=False).returncode
    status = subprocess.run(["ubuntu-drivers", "install"], check=False).returncode
    if have("fwupdmgr"):
        subprocess.run(["fwupdmgr", "refresh", "--force"], check=False)
    return status


def as_json():
    return json.dumps(summary(), indent=2)
