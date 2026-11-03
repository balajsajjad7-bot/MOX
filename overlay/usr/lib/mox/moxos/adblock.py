"""MOX Ad Block: blocks ad and tracker domains across every app."""
import os
import re
import subprocess
import urllib.request
from pathlib import Path

from .common import ROOT

HOSTS = ROOT / "etc/hosts"
ALLOW = ROOT / "etc/mox/adblock-allow.txt"
SOURCE = "https://raw.githubusercontent.com/StevenBlack/hosts/master/hosts"
START = "# >>> MOX Ad Block >>>"
END = "# <<< MOX Ad Block <<<"
ENTRY = re.compile(r"^0\.0\.0\.0\s+([a-z0-9][a-z0-9.-]*\.[a-z]{2,})\s*(?:#.*)?$", re.I)
KEEP = {"localhost", "local", "broadcasthost"}


class AdBlockError(Exception):
    pass


def parse(text, allowed=()):
    """Keep only 0.0.0.0 block lines, so a list can never redirect a site elsewhere."""
    allowed = {item.strip().lower() for item in allowed if item.strip()}
    domains = set()
    for line in text.splitlines():
        match = ENTRY.match(line.strip())
        if match:
            domain = match[1].lower()
            if domain not in KEEP and domain not in allowed:
                domains.add(domain)
    return sorted(domains)


def strip_block(hosts_text):
    return re.sub(re.escape(START) + r".*?" + re.escape(END) + r"\n?", "", hosts_text, flags=re.S)


def merged(hosts_text, domains):
    base = strip_block(hosts_text).rstrip("\n")
    block = "\n".join(f"0.0.0.0 {domain}" for domain in domains)
    return f"{base}\n{START}\n{block}\n{END}\n"


def blocked_count():
    try:
        return HOSTS.read_text().count("\n0.0.0.0 ")
    except OSError:
        return 0


def allowed():
    try:
        return ALLOW.read_text().splitlines()
    except OSError:
        return []


def _write(text):
    temp = HOSTS.with_suffix(".mox")
    temp.write_text(text)
    temp.chmod(0o644)
    os.replace(temp, HOSTS)
    subprocess.run(["resolvectl", "flush-caches"], check=False, capture_output=True)


def _root(args):
    if os.geteuid() != 0:
        raise AdBlockError("This needs administrator rights. Run: sudo mox adblock " + args)


def update(source_text=None):
    _root("on")
    if source_text is None:
        request = urllib.request.Request(SOURCE, headers={"user-agent": "MOX/0.1"})
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                source_text = response.read().decode("utf-8", "replace")
        except OSError as error:
            raise AdBlockError(f"Couldn't download the block list: {error}") from error
    domains = parse(source_text, allowed())
    if len(domains) < 1000:
        raise AdBlockError("The block list looks wrong, so it was not applied.")
    _write(merged(HOSTS.read_text(), domains))
    return len(domains)


def off():
    _root("off")
    _write(strip_block(HOSTS.read_text()))


def allow(domain):
    _root("allow " + domain)
    domain = domain.strip().lower()
    with open(ALLOW, "a", encoding="utf-8") as handle:
        handle.write(domain + "\n")
    text = HOSTS.read_text()
    _write(re.sub(rf"^0\.0\.0\.0 {re.escape(domain)}\n", "", text, flags=re.M))
