"""MOX Optimizer: tunes the system to the hardware it finds."""
import hashlib
import json
import os
import subprocess
from pathlib import Path

from .common import ROOT, have, run

SYSCTL = ROOT / "etc/sysctl.d/90-mox.conf"
UDEV = ROOT / "etc/udev/rules.d/60-mox-io.rules"
ZRAM = ROOT / "etc/systemd/zram-generator.conf"
PROFILE = ROOT / "etc/profile.d/mox-build.sh"
STAMP = ROOT / "var/lib/mox/optimizer.json"
LITE_DCONF = ROOT / "etc/dconf/db/local.d/50-mox-lite"
MODE = ROOT / "etc/mox/performance"
USER_UNITS = ROOT / "etc/systemd/user"
# File indexers use the most memory and disk in the background on small PCs.
LITE_USER_OFF = ["localsearch-3.service", "tracker-miner-fs-3.service"]
LITE_SYSTEM_OFF = ["cups-browsed.service", "man-db.timer", "plocate-updatedb.timer", "fwupd-refresh.timer", "apport.service"]
LITE_SETTINGS = """# Written by MOX Optimizer for smaller PCs
[org/gnome/desktop/interface]
enable-animations=false

[org/gnome/shell]
enabled-extensions=['ubuntu-dock@ubuntu.com','ubuntu-appindicators@ubuntu.com','mox-widgets@mox.os','GPaste@gnome-shell-extensions.gnome.org']

[org/gnome/shell/extensions/dash-to-dock]
animation-time=0.0
hide-delay=0.0
show-delay=0.0
"""


def detect():
    memory = int(Path("/proc/meminfo").read_text().split()[1]) / 1048576
    disks = []
    for path in Path("/sys/block").glob("*"):
        if path.name.startswith(("loop", "ram", "zram", "sr", "fd", "dm-")):
            continue
        try:
            rotational = (path / "queue/rotational").read_text().strip() == "1"
        except OSError:
            continue
        kind = "nvme" if path.name.startswith("nvme") else "hdd" if rotational else "ssd"
        disks.append({"name": path.name, "kind": kind})
    batteries = list(Path("/sys/class/power_supply").glob("BAT*"))
    return {"memory_gb": round(memory, 1), "cores": os.cpu_count() or 1, "disks": sorted(disks, key=lambda d: d["name"]), "laptop": bool(batteries)}


def chosen_mode():
    try:
        mode = MODE.read_text().strip()
    except OSError:
        return "auto"
    return mode if mode in ("lite", "full") else "auto"


def is_lite(hardware, mode="auto"):
    if mode != "auto":
        return mode == "lite"
    return hardware["memory_gb"] <= 8.5 or hardware["cores"] <= 4


def plan(hardware, mode="auto"):
    """Work out settings from hardware. Nothing here touches the system."""
    memory = hardware["memory_gb"]
    kinds = {disk["kind"] for disk in hardware["disks"]}
    swappiness = 150 if memory < 8 else 80 if memory < 16 else 30
    settings = {
        "vm.swappiness": swappiness,
        "vm.vfs_cache_pressure": 50,
        "vm.page-cluster": 0,
        "vm.dirty_background_ratio": 5 if memory >= 16 else 10,
        "vm.dirty_ratio": 15 if memory >= 16 else 20,
        "fs.inotify.max_user_watches": 524288,
        "net.core.default_qdisc": "fq",
        "net.ipv4.tcp_congestion_control": "bbr",
    }
    return {
        "sysctl": settings,
        "schedulers": {"nvme": "none", "ssd": "mq-deadline", "hdd": "bfq"},
        "zram_mb": int(min(memory * 0.75, 16) * 1024),
        "trim": bool(kinds & {"nvme", "ssd"}),
        "power": "balanced" if hardware["laptop"] else "performance",
        "build_jobs": hardware["cores"],
        "lite": is_lite(hardware, mode),
    }


def render(settings):
    sysctl = "# Written by MOX Optimizer\n" + "".join(f"{key} = {value}\n" for key, value in settings["sysctl"].items())
    rules = "# Written by MOX Optimizer\n"
    rules += 'ACTION=="add|change", KERNEL=="nvme[0-9]*n[0-9]*", ATTR{queue/scheduler}="%s"\n' % settings["schedulers"]["nvme"]
    rules += 'ACTION=="add|change", KERNEL=="sd[a-z]*|mmcblk[0-9]*", ATTR{queue/rotational}=="0", ATTR{queue/scheduler}="%s"\n' % settings["schedulers"]["ssd"]
    rules += 'ACTION=="add|change", KERNEL=="sd[a-z]*", ATTR{queue/rotational}=="1", ATTR{queue/scheduler}="%s"\n' % settings["schedulers"]["hdd"]
    zram = f"[zram0]\nzram-size = {settings['zram_mb']}\ncompression-algorithm = zstd\n"
    jobs = settings["build_jobs"]
    profile = f'export MAKEFLAGS="-j{jobs}"\nexport CMAKE_BUILD_PARALLEL_LEVEL={jobs}\n'
    files = {SYSCTL: sysctl, UDEV: rules, ZRAM: zram, PROFILE: profile}
    if settings.get("lite"):
        files[LITE_DCONF] = LITE_SETTINGS
    return files


def _quiet(command, timeout=10):
    """Run a tuning step. One stuck service must never hold up startup."""
    try:
        subprocess.run(command, check=False, capture_output=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        pass


def fingerprint(hardware, mode="auto"):
    return hashlib.sha256(json.dumps([hardware, mode], sort_keys=True).encode()).hexdigest()


def _apply_lite(lite):
    USER_UNITS.mkdir(parents=True, exist_ok=True)
    for unit in LITE_USER_OFF:
        link = USER_UNITS / unit
        if lite and not link.is_symlink() and not link.exists():
            link.symlink_to("/dev/null")
        elif not lite and link.is_symlink():
            link.unlink()
    if not lite:
        LITE_DCONF.unlink(missing_ok=True)
    action = "disable" if lite else "enable"
    _quiet(["systemctl", action, "--no-block", "--now"] + LITE_SYSTEM_OFF)
    _quiet(["dconf", "update"])


def apply(auto=False, mode=None):
    """Write and apply settings. With auto, do nothing if the hardware hasn't changed."""
    if mode:
        MODE.parent.mkdir(parents=True, exist_ok=True)
        MODE.write_text(mode + "\n")
    mode = chosen_mode()
    hardware = detect()
    mark = fingerprint(hardware, mode)
    if auto and STAMP.exists() and json.loads(STAMP.read_text()).get("hardware") == mark:
        return None
    settings = plan(hardware, mode)
    for path, text in render(settings).items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    STAMP.parent.mkdir(parents=True, exist_ok=True)
    STAMP.write_text(json.dumps({"hardware": mark, "settings": settings}))
    _apply_lite(settings["lite"])
    _quiet(["sysctl", "--system"])
    _quiet(["udevadm", "control", "--reload"])
    _quiet(["udevadm", "trigger", "--subsystem-match=block"])
    _quiet(["systemctl", "daemon-reload"])
    if settings["trim"]:
        _quiet(["systemctl", "enable", "--now", "fstrim.timer"])
    if have("powerprofilesctl"):
        _quiet(["powerprofilesctl", "set", settings["power"]])
    return settings


def describe(settings):
    return (
        f"Memory swap: {settings['sysctl']['vm.swappiness']} swappiness, {settings['zram_mb']} MB compressed RAM swap\n"
        f"Disks: NVMe {settings['schedulers']['nvme']}, SSD {settings['schedulers']['ssd']}, hard disk {settings['schedulers']['hdd']}\n"
        f"SSD trim: {'on' if settings['trim'] else 'off'}\n"
        f"Power: {settings['power']}\n"
        f"Compile jobs: {settings['build_jobs']}\n"
        f"Desktop: {'lite, for speed. Log out to see it' if settings.get('lite') else 'full effects'}\n"
        "Network: BBR with fair queueing"
    )
