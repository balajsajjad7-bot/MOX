"""MOX Shield: firewall, antivirus and rootkit checks in one command."""
import os
import subprocess
from pathlib import Path

from .common import have, run

LOG = Path.home() / ".cache/mox/shield-scan.log"


def sudo(command):
    return (["pkexec"] if os.geteuid() != 0 else []) + command


def firewall_enabled(conf=Path("/etc/ufw/ufw.conf")):
    try:
        return "ENABLED=yes" in conf.read_text()
    except OSError:
        return False


def signature_age_days():
    newest = 0
    for name in ("daily.cld", "daily.cvd", "main.cvd", "main.cld"):
        path = Path("/var/lib/clamav") / name
        if path.exists():
            newest = max(newest, path.stat().st_mtime)
    if not newest:
        return None
    import time
    return int((time.time() - newest) / 86400)


def status():
    age = signature_age_days()
    return {
        "firewall": "on" if firewall_enabled() else "off",
        "antivirus": "ready" if have("clamscan") else "missing",
        "virus_signatures": "not downloaded yet" if age is None else f"{age} days old",
        "rootkit_checks": "ready" if have("rkhunter") and have("chkrootkit") else "missing",
        "blocked_today": blocked_today(),
    }


def blocked_today():
    text = run(["journalctl", "-k", "--since", "today", "--grep", "UFW BLOCK", "--no-pager", "-q"], timeout=10)
    return sum(1 for line in text.splitlines() if "UFW BLOCK" in line)


def scan(path):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    command = ["clamscan", "--recursive", "--infected", "--exclude-dir=^/sys|^/proc|^/dev", f"--log={LOG}", str(path)]
    code = subprocess.run(command, check=False).returncode
    print({0: "No threats found.", 1: f"Threats found. See {LOG}."}.get(code, "The scan could not finish. Run 'mox shield update' first."))
    return code


def update():
    return subprocess.run(sudo(["sh", "-c", "systemctl stop clamav-freshclam; freshclam; systemctl start clamav-freshclam"]), check=False).returncode


def rootkit_check():
    return subprocess.run(sudo(["sh", "-c", "chkrootkit -q; rkhunter --check --skip-keypress --report-warnings-only"]), check=False).returncode


def set_firewall(enabled):
    return subprocess.run(sudo(["ufw", "enable" if enabled else "disable"]), check=False).returncode
