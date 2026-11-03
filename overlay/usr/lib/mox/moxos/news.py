"""Headlines from the news feeds listed in /etc/mox/mox.conf."""
import urllib.request
import xml.etree.ElementTree as ET

from .common import config

ATOM = "{http://www.w3.org/2005/Atom}"


def parse(xml_text, limit=8):
    root = ET.fromstring(xml_text)
    items = []
    for entry in root.iter("item"):
        items.append({"title": (entry.findtext("title") or "").strip(), "link": (entry.findtext("link") or "").strip()})
    for entry in root.iter(ATOM + "entry"):
        link = entry.find(ATOM + "link")
        items.append({"title": (entry.findtext(ATOM + "title") or "").strip(), "link": link.get("href", "") if link is not None else ""})
    return [item for item in items if item["title"] and item["link"].startswith(("http://", "https://"))][:limit]


def fetch(url):
    request = urllib.request.Request(url, headers={"user-agent": "MOX/0.1"})
    with urllib.request.urlopen(request, timeout=20) as response:
        return parse(response.read())


def all_sources():
    parser = config()
    results = {}
    for name, url in parser.items("news") if parser.has_section("news") else []:
        try:
            results[name] = fetch(url)
        except (OSError, ET.ParseError):
            results[name] = []
    return results
