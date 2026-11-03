"""Writes live numbers for the MOX desktop widgets."""
import json
import os
import time
from pathlib import Path

from . import net, shield

OUT = Path.home() / ".cache/mox/widgets.json"
FEED_SECONDS = 900


def compose(rates, threat, speed, blocked):
    return {
        "down": net.human_rate(rates[0]),
        "up": net.human_rate(rates[1]),
        "speed": f"{speed['download_mbps']:.0f} ↓  {speed['upload_mbps']:.0f} ↑ Mbps" if speed else "Run: mox speed",
        "blocked": blocked,
        "botnets": threat.get("active"),
        "family": threat.get("top_family", ""),
        "country": threat.get("top_country", ""),
        "exploit": threat.get("latest_exploit", ""),
        "feed_ok": "active" in threat or "latest_exploit" in threat,
    }


def read_speed():
    try:
        return json.loads((net.CACHE / "speed.json").read_text())
    except (OSError, ValueError):
        return None


def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    last = net.interface_bytes()
    threat = {}
    next_feed = 0.0
    while True:
        time.sleep(2)
        now = net.interface_bytes()
        rates = ((now[0] - last[0]) / 2, (now[1] - last[1]) / 2)
        last = now
        if time.monotonic() >= next_feed:
            threat = net.threats()
            blocked = shield.blocked_today()
            next_feed = time.monotonic() + FEED_SECONDS
        temp = OUT.with_suffix(".tmp")
        temp.write_text(json.dumps(compose(rates, threat, read_speed(), blocked)))
        os.replace(temp, OUT)
