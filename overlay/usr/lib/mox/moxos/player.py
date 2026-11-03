"""MOX Player: one app that opens any file with the right engine."""
import shutil
import subprocess
import sys
from pathlib import Path

from .common import notify, run
from .runner import SUFFIXES

VIDEO_SUFFIXES = {".mp4", ".mp5", ".mkv", ".avi", ".mov", ".webm", ".flv", ".wmv", ".m4v", ".mpg", ".mpeg", ".ts", ".m2ts", ".3gp", ".ogv", ".vob", ".rmvb", ".divx", ".mts"}
AUDIO_SUFFIXES = {".mp3", ".flac", ".wav", ".aac", ".m4a", ".ogg", ".opus", ".wma", ".alac", ".aiff", ".ape", ".amr", ".mid", ".midi"}
BOOKS = {".epub", ".mobi", ".azw3", ".fb2"}
DOCS = {".pdf", ".djvu", ".cbz", ".cbr", ".xps", ".tiff"}
OFFICE = {".doc", ".docx", ".odt", ".rtf", ".xls", ".xlsx", ".ods", ".csv", ".ppt", ".pptx", ".odp"}
ARCHIVES = {".zip", ".rar", ".7z", ".tar", ".gz", ".xz", ".zst", ".bz2", ".tgz", ".iso", ".cab"}


def route(path, mime):
    """Choose the command for a file from its real type, then its name."""
    suffix = Path(path).suffix.lower()
    if suffix in SUFFIXES and SUFFIXES[suffix] not in ("python", "script"):
        return ["mox-run", path]
    if mime.startswith(("video/", "audio/")) or suffix in VIDEO_SUFFIXES or suffix in AUDIO_SUFFIXES:
        return ["mpv", "--force-window=yes", "--player-operation-mode=pseudo-gui", path]
    if suffix in BOOKS:
        return ["foliate", path]
    if mime == "application/pdf" or suffix in DOCS:
        return ["papers", path]
    if suffix in OFFICE or "officedocument" in mime or "opendocument" in mime or mime in ("application/msword", "application/vnd.ms-excel", "application/vnd.ms-powerpoint"):
        return ["libreoffice", path]
    if mime.startswith("image/"):
        return ["loupe", path]
    if suffix in ARCHIVES or mime in ("application/zip", "application/x-7z-compressed", "application/x-rar", "application/gzip", "application/x-xz", "application/x-tar"):
        return ["file-roller", path]
    if mime.startswith("text/") or mime in ("application/json", "application/xml", "application/javascript", "inode/x-empty"):
        return ["gnome-text-editor", path]
    return []


def open_file(path):
    if not Path(path).exists():
        notify("MOX Player", f"{path} wasn't found.")
        return 1
    mime = run(["file", "--brief", "--mime-type", path]).strip()
    command = route(path, mime)
    if not command or shutil.which(command[0]) is None:
        notify("MOX Player can't open this file", f"Its type is {mime or 'unknown'}, and no installed app can read it.")
        return 2
    return subprocess.run(command, check=False).returncode


def main():
    if len(sys.argv) > 1:
        return max(open_file(path) for path in sys.argv[1:])
    done = subprocess.run(["zenity", "--file-selection", "--title=MOX Player"], capture_output=True, text=True, check=False)
    return open_file(done.stdout.strip()) if done.stdout.strip() else 0
