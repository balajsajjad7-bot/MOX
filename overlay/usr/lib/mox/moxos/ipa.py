"""Inspect an iPhone .ipa file without running it.

The result says whether touchHLE, the only open source iOS layer for PCs, can
try the app. It only handles 32-bit iPhone OS 2 and 3 apps that are not
encrypted, so the check runs first and gives a clear reason instead of a crash.
"""
import plistlib
import struct
import zipfile
from dataclasses import dataclass, field

CPU_ARM = 12
CPU_ARM64 = 0x0100000C
LC_ENCRYPTION_INFO = 0x21
LC_ENCRYPTION_INFO_64 = 0x2C
THIN = {0xFEEDFACE: False, 0xFEEDFACF: True, 0xCEFAEDFE: False, 0xCFFAEDFE: True}


@dataclass
class IpaReport:
    name: str = "Unknown app"
    min_os: str = ""
    arches: list = field(default_factory=list)
    encrypted: bool = False
    supported: bool = False
    reason: str = ""


def _thin_slice(data, offset):
    """Return (cpu type, encrypted) for one Mach-O image at offset."""
    magic_be = struct.unpack_from(">I", data, offset)[0]
    if magic_be not in THIN:
        raise ValueError("not a Mach-O image")
    little = magic_be in (0xCEFAEDFE, 0xCFFAEDFE)
    is64 = THIN[magic_be]
    end = "<" if little else ">"
    cpu = struct.unpack_from(end + "I", data, offset + 4)[0]
    ncmds = struct.unpack_from(end + "I", data, offset + 16)[0]
    pos = offset + (32 if is64 else 28)
    encrypted = False
    for _ in range(ncmds):
        cmd, size = struct.unpack_from(end + "II", data, pos)
        if cmd in (LC_ENCRYPTION_INFO, LC_ENCRYPTION_INFO_64):
            encrypted = encrypted or struct.unpack_from(end + "I", data, pos + 16)[0] != 0
        if size < 8:
            break
        pos += size
    return cpu, encrypted


def macho_slices(data):
    """List (cpu type, encrypted) for every architecture in a Mach-O file."""
    magic = struct.unpack_from(">I", data, 0)[0]
    if magic == 0xCAFEBABE:
        count = struct.unpack_from(">I", data, 4)[0]
        return [
            _thin_slice(data, struct.unpack_from(">IIIII", data, 8 + i * 20)[2])
            for i in range(count)
        ]
    return [_thin_slice(data, 0)]


def inspect(path):
    report = IpaReport()
    try:
        with zipfile.ZipFile(path) as archive:
            plists = [n for n in archive.namelist() if n.count("/") == 2 and n.endswith(".app/Info.plist") and n.startswith("Payload/")]
            if not plists:
                report.reason = "This file has no iPhone app inside it."
                return report
            info = plistlib.loads(archive.read(plists[0]))
            report.name = info.get("CFBundleDisplayName") or info.get("CFBundleName") or report.name
            report.min_os = str(info.get("MinimumOSVersion", ""))
            binary = archive.read(plists[0].rsplit("/", 1)[0] + "/" + info["CFBundleExecutable"])
    except (zipfile.BadZipFile, KeyError, ValueError, plistlib.InvalidFileException, OSError) as error:
        report.reason = f"This file could not be read as an iPhone app ({error})."
        return report

    try:
        slices = macho_slices(binary)
    except (struct.error, ValueError) as error:
        report.reason = f"The app's program could not be read ({error})."
        return report

    report.arches = ["arm64" if cpu == CPU_ARM64 else "armv7" if cpu == CPU_ARM else hex(cpu) for cpu, _ in slices]
    report.encrypted = any(encrypted for _, encrypted in slices)
    if CPU_ARM not in [cpu for cpu, _ in slices]:
        report.reason = "This is a modern 64-bit iPhone app. No open source tool can run these on a PC yet."
    elif report.encrypted:
        report.reason = "This app is encrypted by the App Store, so it cannot run outside an iPhone."
    elif report.min_os and int(report.min_os.split(".")[0] or 0) > 3:
        report.reason = f"This app needs iOS {report.min_os}. touchHLE supports iPhone OS 2 and 3 apps."
    else:
        report.supported = True
    return report
