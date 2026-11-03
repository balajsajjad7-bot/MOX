"""MOX Health: one report for disks, heat, battery, memory and services."""
import json
import os
import re
import shutil
from pathlib import Path

from .common import have, run

HELPER = "/usr/lib/mox/disk-health"


def read_smart(data):
    """Reduce smartctl JSON to what matters."""
    nvme = data.get("nvme_smart_health_information_log") or {}
    passed = (data.get("smart_status") or {}).get("passed")
    disk = {
        "model": data.get("model_name") or "Unknown disk",
        "passed": passed,
        "temperature_c": (data.get("temperature") or {}).get("current"),
        "power_on_hours": (data.get("power_on_time") or {}).get("hours"),
        "wear_percent": nvme.get("percentage_used"),
        "spare_percent": nvme.get("available_spare"),
        "media_errors": nvme.get("media_errors"),
        "unsafe_shutdowns": nvme.get("unsafe_shutdowns"),
    }
    for attribute in (data.get("ata_smart_attributes") or {}).get("table", []):
        name = attribute.get("name", "")
        if name == "Reallocated_Sector_Ct":
            disk["bad_sectors"] = (attribute.get("raw") or {}).get("value")
        if name in ("Wear_Leveling_Count", "Media_Wearout_Indicator", "Percent_Lifetime_Remain") and disk["wear_percent"] is None:
            disk["wear_percent"] = 100 - int(attribute.get("value", 100))
    return disk


def verdict(disk):
    if disk["passed"] is False or (disk.get("media_errors") or 0) > 0 or (disk.get("bad_sectors") or 0) > 0:
        return "Failing, back up now"
    if disk["passed"] is None:
        return "Unknown"
    if (disk.get("wear_percent") or 0) >= 90:
        return "Worn, plan to replace"
    return "Healthy"


def disks():
    names = [p.name for p in Path("/sys/block").glob("*") if not p.name.startswith(("loop", "ram", "zram", "sr", "fd", "dm-"))]
    found = []
    for name in sorted(names):
        command = [HELPER, name] if os.geteuid() == 0 else ["sudo", "-n", HELPER, name]
        text = run(command, timeout=30)
        try:
            disk = read_smart(json.loads(text))
        except ValueError:
            disk = read_smart({})
        disk["device"] = name
        disk["verdict"] = verdict(disk)
        found.append(disk)
    return found


def battery():
    for path in Path("/sys/class/power_supply").glob("BAT*"):
        def number(*names):
            for name in names:
                try:
                    return int((path / name).read_text())
                except (OSError, ValueError):
                    continue
            return 0
        full, design = number("energy_full", "charge_full"), number("energy_full_design", "charge_full_design")
        if design:
            return {"health_percent": round(full * 100 / design), "cycles": number("cycle_count")}
    return None


def hottest_cpu(text):
    temps = []
    for chip in (json.loads(text) if text else {}).values():
        if isinstance(chip, dict):
            for sensor in chip.values():
                if isinstance(sensor, dict):
                    temps += [value for key, value in sensor.items() if key.endswith("_input") and "temp" in key]
    return round(max(temps)) if temps else None


def memory_usage():
    values = {}
    for line in Path("/proc/meminfo").read_text().splitlines():
        key, _, rest = line.partition(":")
        values[key] = int(rest.split()[0])
    return round((1 - values["MemAvailable"] / values["MemTotal"]) * 100)


def report():
    total, used, _free = shutil.disk_usage("/")
    failed = [line.split()[0].lstrip("●") for line in run(["systemctl", "--failed", "--no-legend", "--plain"]).splitlines() if line.strip()]
    upgrades = run(["apt", "list", "--upgradable"], timeout=30).count("\n")
    try:
        sensors = hottest_cpu(run(["sensors", "-j"]))
    except ValueError:
        sensors = None
    return {
        "disks": disks(),
        "battery": battery(),
        "cpu_temperature_c": sensors,
        "load": round(os.getloadavg()[0], 2),
        "memory_used_percent": memory_usage(),
        "system_disk_used_percent": round(used * 100 / total),
        "failed_services": failed,
        "updates_waiting": max(upgrades - 1, 0),
    }


def text(data):
    lines = []
    for disk in data["disks"]:
        lines.append(f"{disk['device']}: {disk['model']} - {disk['verdict']}")
        details = []
        if disk["temperature_c"] is not None:
            details.append(f"{disk['temperature_c']}°C")
        if disk["wear_percent"] is not None:
            details.append(f"{disk['wear_percent']}% worn")
        if disk["spare_percent"] is not None:
            details.append(f"{disk['spare_percent']}% spare")
        if disk["power_on_hours"] is not None:
            details.append(f"{disk['power_on_hours']} hours on")
        if details:
            lines.append("  " + ", ".join(details))
    if data["battery"]:
        lines.append(f"Battery: {data['battery']['health_percent']}% of original capacity, {data['battery']['cycles']} cycles")
    if data["cpu_temperature_c"] is not None:
        lines.append(f"CPU: {data['cpu_temperature_c']}°C")
    lines.append(f"Memory: {data['memory_used_percent']}% used")
    lines.append(f"System disk: {data['system_disk_used_percent']}% used")
    lines.append(f"Load: {data['load']}")
    lines.append("Failed services: " + (", ".join(data["failed_services"]) or "none"))
    lines.append(f"Updates waiting: {data['updates_waiting']}")
    return "\n".join(lines)
