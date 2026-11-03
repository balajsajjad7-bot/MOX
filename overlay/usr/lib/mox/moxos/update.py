"""Creator-signed updates.

An update is accepted only if manifest.json has a valid Ed25519 signature from
the creator's key, is newer than the installed version, and its archive matches
the signed hash. Nothing else on the machine can publish an official update.
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path

from .common import PUBKEY, ROOT, VERSION_FILE, config, version


class UpdateError(Exception):
    pass


def parse_version(text):
    try:
        return tuple(int(part) for part in text.strip().split("."))
    except ValueError as error:
        raise UpdateError(f"Bad version number: {text!r}") from error


def verify_signature(manifest, signature, pubkey=PUBKEY):
    if not Path(pubkey).is_file():
        raise UpdateError("The creator's public key is missing, so no update can be trusted.")
    done = subprocess.run(
        ["openssl", "pkeyutl", "-verify", "-pubin", "-inkey", str(pubkey), "-rawin", "-in", str(manifest), "-sigfile", str(signature)],
        capture_output=True, check=False,
    )
    if done.returncode != 0:
        raise UpdateError("Signature check failed. This update did not come from the creator.")


def _fetch(url, destination):
    if url.startswith("file://"):
        shutil.copyfile(url[7:], destination)
        return
    with urllib.request.urlopen(url, timeout=60) as response, open(destination, "wb") as out:
        shutil.copyfileobj(response, out)


def load_manifest(work, url=None):
    """Download and verify the manifest. Returns its parsed contents."""
    url = url or config()["updates"]["manifest_url"]
    manifest, signature = work / "manifest.json", work / "manifest.json.sig"
    try:
        _fetch(url, manifest)
        _fetch(url + ".sig", signature)
    except OSError as error:
        raise UpdateError(f"Couldn't download the update information: {error}") from error
    verify_signature(manifest, signature)
    return json.loads(manifest.read_text())


def machine_bucket(machine_id_path=Path("/etc/machine-id")):
    """A stable number from 0 to 99 for this computer, used for gradual rollouts."""
    try:
        seed = Path(machine_id_path).read_text().strip()
    except OSError:
        seed = "unknown"
    return int(hashlib.sha256(seed.encode()).hexdigest()[:8], 16) % 100


def wanted(manifest, bucket=None):
    """Whether this computer should take the release: not paused, newer, and inside the rollout."""
    if manifest.get("paused"):
        return False
    if parse_version(manifest["version"]) <= parse_version(version()):
        return False
    rollout = int(manifest.get("rollout", 100))
    return (machine_bucket() if bucket is None else bucket) < rollout


def check(url=None):
    """Return the manifest if a signed release is ready for this computer, otherwise None."""
    with tempfile.TemporaryDirectory() as folder:
        manifest = load_manifest(Path(folder), url)
    return manifest if wanted(manifest) else None


def _safe_extract(archive, target):
    with tarfile.open(archive) as bundle:
        bundle.extractall(target, filter="data")


def healthy(code):
    """Make sure the new MOX code still starts before keeping it."""
    subprocess.run(
        [sys.executable, "-c", f"import sys; sys.path.insert(0, {str(code)!r}); import moxos.cli"],
        check=True, capture_output=True, timeout=60,
    )


def apply(url=None):
    """Install the newest signed release. Returns the new version, or None."""
    if os.geteuid() != 0:
        raise UpdateError("Installing an update needs administrator rights. Run 'sudo mox update'.")
    with tempfile.TemporaryDirectory() as folder:
        work = Path(folder)
        manifest = load_manifest(work, url)
        if not wanted(manifest):
            return None
        archive = work / "update.tar.gz"
        base = (url or config()["updates"]["manifest_url"]).rsplit("/", 1)[0]
        _fetch(manifest["url"] if "://" in manifest["url"] else f"{base}/{manifest['url']}", archive)
        if hashlib.sha256(archive.read_bytes()).hexdigest() != manifest["sha256"]:
            raise UpdateError("The download doesn't match the signed release, so it was rejected.")
        staged = work / "staged"
        staged.mkdir()
        _safe_extract(archive, staged)
        code = ROOT / "usr/lib/mox"
        backup = work / "previous"
        if code.is_dir():
            shutil.copytree(code, backup, symlinks=True)
        try:
            files = staged / "rootfs"
            if files.is_dir():
                shutil.copytree(files, ROOT, dirs_exist_ok=True, symlinks=True)
            script = staged / "post-install.sh"
            if script.is_file():
                subprocess.run(["bash", str(script)], check=True, cwd=staged)
            healthy(code)
        except (subprocess.CalledProcessError, OSError) as error:
            if backup.is_dir():
                shutil.rmtree(code, ignore_errors=True)
                shutil.copytree(backup, code, symlinks=True)
            raise UpdateError(f"The update failed its check, so MOX kept the old version: {error}") from error
        VERSION_FILE.parent.mkdir(parents=True, exist_ok=True)
        VERSION_FILE.write_text(manifest["version"] + "\n")
        return manifest["version"]
