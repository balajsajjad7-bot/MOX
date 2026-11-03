"""MOX Troubleshooter: known safe fixes first, then AI with your approval."""
import os
import shutil
import subprocess

from .common import have, run

# Each problem has checks that report what's wrong, and safe fixes that can run on their own.
# Nothing here deletes personal files or changes security settings.
PROBLEMS = {
    "desktop": {
        "label": "Dock, taskbar or widgets look wrong",
        "user_fixes": [
            ("Turn off the Windows-style taskbar", ["gnome-extensions", "disable", "window-list@gnome-shell-extensions.gcampax.github.com"]),
            ("Restore the MOX desktop", ["gsettings", "reset", "org.gnome.shell", "enabled-extensions"]),
            ("Restart the widgets", ["systemctl", "--user", "restart", "mox-widgets"]),
        ],
        "fixes": [],
        "check": ["sh", "-c", "gsettings get org.gnome.shell enabled-extensions | grep -q window-list || echo ok"],
    },
    "android": {
        "label": "Android apps won't start",
        "fixes": [
            ("Load the Android driver", ["modprobe", "binder_linux"]),
            ("Download Android", ["sh", "-c", "[ -f /var/lib/waydroid/images/system.img ] || waydroid init"]),
            ("Restart Android", ["systemctl", "restart", "waydroid-container"]),
        ],
        "check": ["sh", "-c", "[ -f /var/lib/waydroid/images/system.img ] && systemctl is-active --quiet waydroid-container && echo ok"],
    },
    "internet": {
        "label": "Internet isn't working",
        "fixes": [
            ("Restart networking", ["systemctl", "restart", "NetworkManager"]),
            ("Flush the DNS cache", ["resolvectl", "flush-caches"]),
            ("Restart name resolution", ["systemctl", "restart", "systemd-resolved"]),
        ],
        "check": ["sh", "-c", "curl -fsS -m 8 -o /dev/null https://archive.ubuntu.com && echo ok"],
    },
    "sound": {
        "label": "No sound",
        "user_fixes": [("Restart the sound system", ["systemctl", "--user", "restart", "pipewire", "pipewire-pulse", "wireplumber"])],
        "fixes": [],
        "check": ["sh", "-c", "pactl info >/dev/null && echo ok"],
    },
    "bluetooth": {
        "label": "Bluetooth isn't working",
        "fixes": [("Unblock radios", ["rfkill", "unblock", "bluetooth"]), ("Restart Bluetooth", ["systemctl", "restart", "bluetooth"])],
        "check": ["sh", "-c", "bluetoothctl show | grep -q 'Powered: yes' && echo ok"],
    },
    "wifi": {
        "label": "WiFi is off or missing",
        "fixes": [("Unblock radios", ["rfkill", "unblock", "wifi"]), ("Turn WiFi on", ["nmcli", "radio", "wifi", "on"]), ("Restart networking", ["systemctl", "restart", "NetworkManager"])],
        "check": ["sh", "-c", "nmcli radio wifi | grep -q enabled && echo ok"],
    },
    "updates": {
        "label": "Updates or installs are stuck",
        "fixes": [
            ("Finish interrupted installs", ["dpkg", "--configure", "-a"]),
            ("Repair missing packages", ["apt-get", "-f", "install", "-y"]),
            ("Refresh package lists", ["apt-get", "update"]),
        ],
        "check": ["sh", "-c", "apt-get check >/dev/null 2>&1 && echo ok"],
    },
    "disk": {
        "label": "Disk is full",
        "fixes": [
            ("Clean the package cache", ["apt-get", "clean"]),
            ("Shrink old system logs", ["journalctl", "--vacuum-size=200M"]),
            ("Remove unused packages", ["apt-get", "autoremove", "-y"]),
            ("Remove unused app runtimes", ["flatpak", "uninstall", "--unused", "-y"]),
        ],
        "check": ["sh", "-c", "[ $(df --output=pcent / | tail -1 | tr -dc 0-9) -lt 95 ] && echo ok"],
    },
    "slow": {
        "label": "The PC is slow",
        "fixes": [("Re-tune for this hardware", ["mox", "optimize"]), ("Restart failed services", ["systemctl", "reset-failed"])],
        "check": ["sh", "-c", "echo ok"],
    },
    "printer": {
        "label": "Printer isn't working",
        "fixes": [("Restart printing", ["systemctl", "restart", "cups"]), ("Clear stuck print jobs", ["cancel", "-a"])],
        "check": ["sh", "-c", "lpstat -r | grep -q 'is running' && echo ok"],
    },
    "drivers": {
        "label": "A device has no driver",
        "fixes": [("Install recommended drivers", ["ubuntu-drivers", "install"]), ("Update firmware lists", ["fwupdmgr", "refresh", "--force"])],
        "check": ["sh", "-c", "echo ok"],
    },
}


def is_fixed(name):
    return run(PROBLEMS[name]["check"], timeout=30).strip().endswith("ok")


def failed_services():
    return [line.split()[0] for line in run(["systemctl", "--failed", "--no-legend", "--plain"]).splitlines() if line.strip()]


def repair(name, log=print):
    """Run the safe fixes for one problem until its check passes. Returns True when fixed."""
    problem = PROBLEMS[name]
    if is_fixed(name) and name not in ("slow", "drivers"):
        log(f"{problem['label']}: no problem found.")
        return True
    for label, command in problem.get("user_fixes", []):
        log(f"Trying: {label}")
        subprocess.run(command, check=False, capture_output=True)
        if is_fixed(name):
            log("Fixed.")
            return True
    root = os.geteuid() == 0
    for label, command in problem["fixes"]:
        if not have(command[0]):
            continue
        log(f"Trying: {label}")
        subprocess.run(command if root else ["pkexec"] + command, check=False, capture_output=True)
        if is_fixed(name) and name not in ("slow", "drivers"):
            log("Fixed.")
            return True
    if name in ("slow", "drivers"):
        log("Done.")
        return True
    log("The usual fixes didn't solve it.")
    return False


def describe_for_ai(name):
    lines = [f"Problem: {PROBLEMS[name]['label']}", "Failed services: " + (", ".join(failed_services()) or "none")]
    if name in ("internet", "wifi"):
        lines.append(run(["nmcli", "-t", "device", "status"]))
    if name == "sound":
        lines.append(run(["pactl", "list", "short", "sinks"]))
    if name == "bluetooth":
        lines.append(run(["rfkill", "list"]))
    if name == "disk":
        lines.append(run(["df", "-h", "/"]))
    return "\n".join(lines)[:3000]
