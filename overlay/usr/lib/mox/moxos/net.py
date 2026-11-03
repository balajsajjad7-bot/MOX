"""Internet speed and public threat feeds."""
import json
import time
import urllib.request
from collections import Counter
from pathlib import Path

CACHE = Path.home() / ".cache/mox"
FEODO = "https://feodotracker.abuse.ch/downloads/ipblocklist.json"
KEV = "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"
AGENT = {"user-agent": "MOX/0.1"}


def interface_bytes(text=None):
    """Total received and sent bytes, leaving out loopback and virtual links."""
    if text is None:
        text = Path("/proc/net/dev").read_text()
    down = up = 0
    for line in text.splitlines()[2:]:
        name, _, numbers = line.partition(":")
        name = name.strip()
        if name == "lo" or name.startswith(("veth", "docker", "virbr", "lxc")):
            continue
        fields = numbers.split()
        down += int(fields[0])
        up += int(fields[8])
    return down, up


def human_rate(bytes_per_second):
    bits = bytes_per_second * 8
    if bits >= 1_000_000:
        return f"{bits / 1_000_000:.1f} Mbps"
    return f"{bits / 1000:.0f} Kbps"


def speed_test(size=25_000_000):
    """Measure download and upload through Cloudflare's public speed test."""
    start = time.monotonic()
    request = urllib.request.Request(f"https://speed.cloudflare.com/__down?bytes={size}", headers=AGENT)
    received = 0
    with urllib.request.urlopen(request, timeout=60) as response:
        while chunk := response.read(65536):
            received += len(chunk)
    download = received * 8 / (time.monotonic() - start) / 1_000_000
    body = b"0" * (size // 5)
    start = time.monotonic()
    request = urllib.request.Request("https://speed.cloudflare.com/__up", data=body, headers=AGENT, method="POST")
    with urllib.request.urlopen(request, timeout=60):
        pass
    upload = len(body) * 8 / (time.monotonic() - start) / 1_000_000
    result = {"download_mbps": round(download, 1), "upload_mbps": round(upload, 1), "time": int(time.time())}
    CACHE.mkdir(parents=True, exist_ok=True)
    (CACHE / "speed.json").write_text(json.dumps(result))
    return result


def _json(url):
    request = urllib.request.Request(url, headers=AGENT)
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def summarize_botnets(entries):
    online = [item for item in entries if item.get("status") == "online"]
    families = Counter(item.get("malware", "Unknown") for item in online)
    countries = Counter(item.get("country") or "??" for item in online)
    return {
        "active": len(online),
        "top_family": families.most_common(1)[0][0] if families else "",
        "top_country": countries.most_common(1)[0][0] if countries else "",
    }


def latest_exploit(feed):
    items = sorted(feed.get("vulnerabilities", []), key=lambda item: item.get("dateAdded", ""), reverse=True)
    if not items:
        return ""
    item = items[0]
    return f"{item.get('cveID')}: {item.get('vendorProject')} {item.get('product')}"


def threats():
    """Fetch public data. Any source that is down is simply left out."""
    result = {"time": int(time.time())}
    try:
        result.update(summarize_botnets(_json(FEODO)))
    except (OSError, ValueError):
        pass
    try:
        result["latest_exploit"] = latest_exploit(_json(KEV))
    except (OSError, ValueError):
        pass
    return result
