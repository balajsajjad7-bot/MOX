"""Display and power choices."""
import subprocess

from .common import have

PLANS = {
    "saver": {"profile": "power-saver", "blank": 120, "sleep_battery": 600, "sleep_ac": 1800},
    "balanced": {"profile": "balanced", "blank": 300, "sleep_battery": 900, "sleep_ac": 3600},
    "performance": {"profile": "performance", "blank": 900, "sleep_battery": 1800, "sleep_ac": 0},
}


def plan_commands(name):
    plan = PLANS[name]
    power = "org.gnome.settings-daemon.plugins.power"
    commands = [
        ["gsettings", "set", "org.gnome.desktop.session", "idle-delay", str(plan["blank"])],
        ["gsettings", "set", power, "sleep-inactive-battery-timeout", str(plan["sleep_battery"])],
        ["gsettings", "set", power, "sleep-inactive-ac-timeout", str(plan["sleep_ac"])],
        ["gsettings", "set", power, "sleep-inactive-ac-type", "nothing" if plan["sleep_ac"] == 0 else "suspend"],
    ]
    if have("powerprofilesctl"):
        commands.append(["powerprofilesctl", "set", plan["profile"]])
    return commands


def apply_plan(name):
    for command in plan_commands(name):
        subprocess.run(command, check=False, capture_output=True)


def switch_displays():
    """Opens display settings. Super+P also cycles duplicate, extend, external only and built-in only."""
    return subprocess.Popen(["gnome-control-center", "display"])
