"""Wallpapers: the built-in MOX set, or today's trending titles from your own API key.

Trending images stay on your own computer and are never part of the MOX ISO.
"""
import json
import subprocess
import urllib.parse
import urllib.request
from pathlib import Path

from . import vault

FOLDER = Path.home() / ".local/share/mox/wallpapers"
LIVING = "file:///usr/share/backgrounds/mox/mox-living.xml"
AGENT = {"user-agent": "MOX/0.1"}


class WallpaperError(Exception):
    pass


def apply(uri):
    for key in ("picture-uri", "picture-uri-dark"):
        subprocess.run(["gsettings", "set", "org.gnome.desktop.background", key, uri], check=False)


def _json(url):
    request = urllib.request.Request(url, headers=AGENT)
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def pick_title(results, name_key="title"):
    usable = [item for item in results if item.get("backdrop_path") or item.get("background_image")]
    if not usable:
        raise WallpaperError("No trending picture was available.")
    return usable[0]


def trending(kind="movie"):
    if kind in ("movie", "tv"):
        key = vault.get("TMDB_API_KEY")
        if not key:
            raise WallpaperError("Add a free TMDB key first: mox api add TMDB_API_KEY")
        data = _json("https://api.themoviedb.org/3/trending/" + kind + "/week?" + urllib.parse.urlencode({"api_key": key}))
        item = pick_title(data.get("results", []))
        title = item.get("title") or item.get("name") or "Trending title"
        image = "https://image.tmdb.org/t/p/original" + item["backdrop_path"]
        credit = "Image from TMDB. MOX is not endorsed or certified by TMDB."
    elif kind == "game":
        key = vault.get("RAWG_API_KEY")
        if not key:
            raise WallpaperError("Add a free RAWG key first: mox api add RAWG_API_KEY")
        data = _json("https://api.rawg.io/api/games/lists/popular?" + urllib.parse.urlencode({"key": key, "page_size": 10}))
        item = pick_title(data.get("results", []))
        title = item.get("name", "Popular game")
        image = item["background_image"]
        credit = "Image from RAWG."
    else:
        raise WallpaperError("Choose movie, tv or game.")
    FOLDER.mkdir(parents=True, exist_ok=True)
    target = FOLDER / ("trending-" + kind + Path(urllib.parse.urlparse(image).path).suffix)
    with urllib.request.urlopen(urllib.request.Request(image, headers=AGENT), timeout=60) as response:
        target.write_bytes(response.read())
    apply(target.as_uri())
    return title, credit
