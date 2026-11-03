"""MOX WiFi: understand and improve your own wireless connection."""
import re
import subprocess
from collections import Counter

from .common import run

FIELDS = "IN-USE,SSID,CHAN,SIGNAL,SECURITY,FREQ"


def parse_scan(text):
    networks = []
    for line in text.splitlines():
        parts = re.split(r"(?<!\\):", line)
        if len(parts) < 6:
            continue
        in_use, ssid, channel, signal, security, freq = parts[:6]
        try:
            networks.append({"active": in_use.strip() == "*", "ssid": ssid.replace("\\:", ":") or "(hidden)", "channel": int(channel),
                             "signal": int(signal), "security": security or "Open", "band": "5 GHz" if int(re.sub(r"\D", "", freq) or 0) >= 5000 else "2.4 GHz"})
        except ValueError:
            continue
    return networks


def scan():
    return parse_scan(run(["nmcli", "-t", "-f", FIELDS, "device", "wifi", "list", "--rescan", "yes"], timeout=30))


def best_channel(networks, band="2.4 GHz"):
    """The least crowded channel, weighting nearby strong networks more."""
    choices = (1, 6, 11) if band == "2.4 GHz" else (36, 40, 44, 48, 149, 153, 157, 161)
    load = Counter()
    for network in networks:
        if network["band"] != band:
            continue
        for choice in choices:
            if abs(network["channel"] - choice) < (5 if band == "2.4 GHz" else 4):
                load[choice] += network["signal"]
    return min(choices, key=lambda channel: load[channel])


def advice(networks):
    tips = []
    mine = next((n for n in networks if n["active"]), None)
    if mine:
        if mine["signal"] < 40:
            tips.append("Your signal is weak. Move closer to the router or remove obstacles.")
        if mine["security"] in ("Open", "WEP", "--") or "WEP" in mine["security"]:
            tips.append("Your network is unprotected or uses old WEP security. Switch the router to WPA3 or WPA2.")
        best = best_channel(networks, mine["band"])
        if best != mine["channel"]:
            tips.append(f"Channel {best} is less crowded than your channel {mine['channel']}. Change it in your router settings.")
        if mine["band"] == "2.4 GHz" and any(n["ssid"] == mine["ssid"] and n["band"] == "5 GHz" for n in networks):
            tips.append("Your router also offers 5 GHz. It's usually faster when you're close to the router.")
    return tips or ["Your WiFi looks healthy."]


def latency(host="1.1.1.1", count=10):
    text = run(["ping", "-c", str(count), "-i", "0.3", host], timeout=30)
    match = re.search(r"(\d+)% packet loss.*?= [\d.]+/([\d.]+)/[\d.]+/([\d.]+)", text, re.S)
    return {"loss_percent": int(match[1]), "average_ms": float(match[2]), "jitter_ms": float(match[3])} if match else None


def share_qr(ssid):
    """Show a QR code to join the current network, using the saved password."""
    text = run(["nmcli", "-s", "-g", "802-11-wireless-security.psk", "connection", "show", ssid])
    password = text.strip()
    code = f"WIFI:T:WPA;S:{ssid};P:{password};;" if password else f"WIFI:T:nopass;S:{ssid};;"
    return subprocess.run(["qrencode", "-t", "ANSIUTF8", code], check=False).returncode
