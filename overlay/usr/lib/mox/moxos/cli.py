"""The `mox` command."""
import argparse
import getpass
import json
import os
import subprocess
import sys
from pathlib import Path

from . import addons, adblock, freeapis, mail, tools, ai, bot, cloud, connectors, hardware, health, net, optimize, wifi, wipe, fixer, display, shield, themes, update, vault, vpn, wallpaper
from .common import have, run, version

LAYERS = [
    ("Linux", None, "native"),
    ("Windows .exe", "wine", "windows"),
    ("Android .apk", "waydroid", "android"),
    ("Mac apps", "darling", "mac"),
    ("Old iPhone .ipa", "touchHLE", "iphone"),
]
TOOLS = {
    "Languages": ["gcc", "g++", "clang", "python3", "node", "go", "rustc", "java", "ruby", "php", "lua"],
    "Build": ["make", "cmake", "ninja", "gdb", "git", "gh", "docker", "podman", "qemu-system-x86_64"],
    "AI": ["claude", "codex", "ollama", "llama-server"],
    "Network": ["nmcli", "iw", "iperf3", "mtr", "nethogs", "iftop"],
    "Protection": ["ufw", "clamscan", "freshclam", "rkhunter", "chkrootkit", "wg", "openvpn"],
    "Security": ["nmap", "wireshark", "tcpdump", "sqlmap", "hydra", "john", "hashcat", "aircrack-ng", "nikto", "gobuster", "ffuf", "masscan", "radare2", "binwalk", "bettercap", "mitmproxy", "lynis"],
}


def cmd_status(_args):
    print(f"MOX {version()}\n")
    print("Compatibility")
    for label, binary, addon in LAYERS:
        ready = binary is None or have(binary)
        print(f"  {'ready ' if ready else 'add-on'}  {label}" + ("" if ready else f"  (mox get {addon})"))
    for group, names in TOOLS.items():
        found = [name for name in names if have(name)]
        print(f"\n{group}: {len(found)}/{len(names)}")
        print("  " + " ".join(found))
        missing = [name for name in names if name not in found]
        if missing:
            print("  missing: " + " ".join(missing))
    return 0


def cmd_hw(args):
    print(hardware.as_json() if args.json else hardware.text_report(hardware.summary()))
    return 0


def cmd_drivers(args):
    if args.install:
        return hardware.install_drivers()
    data = hardware.summary()
    print(hardware.text_report(data))
    if args.ai:
        if not data["missing_drivers"]:
            print("\nEvery important device already has a driver.")
            return 0
        print("\nOnly the hardware report above is sent to the AI provider you chose.")
        return ai.fix("These devices have no working driver. Find the right Ubuntu 26.04 driver or firmware package.")
    if data["available_drivers"] and not data["missing_drivers"]:
        print("\nRun 'mox drivers --install' to add the drivers listed above.")
    return 0


def cmd_ai(args):
    words = args.prompt
    try:
        if words[:1] == ["key"] and len(words) == 2 and words[1] in ("anthropic", "openai"):
            ai.set_key(words[1], getpass.getpass(f"Paste your {words[1]} API key: ").strip())
            print("Saved. Only your user can read it.")
        elif words[:1] == ["use"] and len(words) == 2:
            ai.save_setting("provider", words[1])
            print(f"MOX AI will use {words[1]}.")
        elif words[:1] == ["model"] and len(words) == 3:
            ai.save_setting(f"{words[1]}_model", words[2])
            print(f"{words[1]} will use {words[2]}.")
        elif words[:1] == ["status"]:
            print(json.dumps(ai.status(), indent=2))
        elif words[:1] == ["fix"] and len(words) > 1:
            return ai.fix(" ".join(words[1:]))
        elif words:
            print(ai.ask(" ".join(words)))
        else:
            print("Try: mox ai why is my wifi slow\n     mox ai fix my sound isn't working\n     mox ai key anthropic\n     mox ai use openai\n     mox ai model anthropic claude-opus-5-5\n     mox ai status")
    except ai.AIError as error:
        print(error, file=sys.stderr)
        return 1
    return 0


def cmd_apps(_args):
    """Say plainly which kinds of app work on this PC, and what to do when one doesn't."""
    for label, binary, addon in LAYERS:
        if binary is None:
            print(f"Ready      {label}")
        elif addons.is_installed(addon):
            print(f"Ready      {label}")
        else:
            print(f"Not ready  {label}. Run: sudo mox get {addon}")
    if addons.is_installed("android"):
        running = subprocess.run(["systemctl", "is-active", "--quiet", "waydroid-container"], check=False).returncode == 0
        print(f"\nAndroid service: {'running' if running else 'stopped. Run: mox fix android'}")
        print("Open the Android app to use it.")
    print("\nMac apps are limited: Darling runs mostly command-line tools, and most windowed apps won't open.")
    print("iPhone apps are limited: only very old ones can run. Modern .ipa files can't.")
    return 0


def cmd_get(args):
    if not args.addon:
        for name, (label, _script) in addons.ADDONS.items():
            print(f"{'*' if addons.is_installed(name) else ' '} {name:12} {label}")
        print("\n* installed")
        return 0
    return addons.install(args.addon)


def cmd_update(args):
    try:
        if args.check:
            manifest = update.check(args.url)
            print(f"MOX {manifest['version']} is available." if manifest else "MOX is up to date.")
            return 0
        done = update.apply(args.url)
        print(f"Updated to MOX {done}." if done else "MOX is up to date.")
        return 0
    except update.UpdateError as error:
        print(error, file=sys.stderr)
        return 1


def cmd_connect(args):
    if args.action == "setup":
        added = connectors.setup()
        print("Added: " + ", ".join(added) if added else "All no-account connectors are already set up.")
        return 0
    if args.action == "list":
        for name, entry in connectors.load()["mcpServers"].items():
            print(f"{name:20} {entry.get('url') or entry.get('command')}")
        print(f"\nConfig file: {connectors.FILE}\nUse with Claude Code: claude --mcp-config {connectors.FILE}")
    elif args.action == "add":
        if not args.name or not args.target:
            print("Usage: mox connect add NAME URL-or-COMMAND [--env KEY=VALUE]", file=sys.stderr)
            return 2
        connectors.add(args.name, args.target, args.env)
        print(f"Added {args.name}.")
    elif not connectors.remove(args.name or ""):
        print(f"No connector named {args.name}.", file=sys.stderr)
        return 1
    return 0


def cmd_modo(_args):
    return subprocess.run(["mox-modo"], check=False).returncode


def cmd_bot(args):
    if args.message:
        print(bot.reply(" ".join(args.message)))
        return 0
    return bot.chat()


def cmd_sync(args):
    flag = Path("/etc/mox/sync-on")
    if args.action == "status":
        print("Automatic updates:", "on" if flag.exists() else "off")
        applied = Path("/var/lib/mox/sync/applied")
        print("Installed:", applied.read_text()[:7] if applied.exists() else "not synced yet")
        return 0
    if os.geteuid() != 0:
        return subprocess.run(["pkexec", "mox", "sync", args.action], check=False).returncode
    if args.action == "on":
        flag.parent.mkdir(parents=True, exist_ok=True)
        flag.touch()
        subprocess.run(["systemctl", "enable", "--now", "mox-sync.timer"], check=False)
        print("MOX will check GitHub for updates every hour.")
        return 0
    if args.action == "off":
        flag.unlink(missing_ok=True)
        print("Automatic updates are off.")
        return 0
    return subprocess.run(["/usr/lib/mox/sync.sh"], check=False).returncode


def cmd_secureboot(args):
    return subprocess.run(["/usr/lib/mox/secureboot.sh", args.action] + ([args.file] if args.file else []), check=False).returncode


def cmd_tool(args):
    try:
        if args.action == "list":
            print("\n".join(tools.installed()) or "No tools yet. Try: mox tool add owner/name")
        elif args.action == "remove":
            tools.remove(args.name or "")
        else:
            owner, name = tools.parse(args.name or "")
            print(f"This downloads {owner}/{name} and runs its setup on your PC. Only add tools you trust.")
            if not args.yes and input("Continue? [y/N] ").strip().lower() != "y":
                return 1
            path, style = tools.install(args.name)
            print(f"Installed to {path} ({style} project)")
    except tools.ToolError as error:
        print(error, file=sys.stderr)
        return 1
    return 0


def cmd_api(args):
    if args.action == "free":
        for name, (label, url) in freeapis.FREE.items():
            print(f"{name:10} {label}\n           {url}")
        print("\nThese need no key. Try one with: curl -s URL")
        return 0
    if args.action == "list":
        for key, value in vault.masked().items():
            print(f"{key:28} {value}")
        print(f"\nEvery new terminal loads these from {vault.ENV_FILE}")
    elif args.action == "add":
        if not args.name:
            print("Usage: mox api add NAME", file=sys.stderr)
            return 2
        try:
            print(f"Saved {vault.add(args.name, getpass.getpass('Paste the key: ').strip())}.")
        except ValueError as error:
            print(error, file=sys.stderr)
            return 2
    elif not vault.remove(args.name or ""):
        print(f"No key named {args.name}.", file=sys.stderr)
        return 1
    return 0


def cmd_speed(_args):
    try:
        result = net.speed_test()
    except OSError as error:
        print(f"The speed test couldn't run: {error}", file=sys.stderr)
        return 1
    print(f"Download {result['download_mbps']} Mbps\nUpload   {result['upload_mbps']} Mbps")
    return 0


def cmd_shield(args):
    if args.action == "status":
        for key, value in shield.status().items():
            print(f"{key.replace('_', ' '):20} {value}")
        return 0
    if args.action == "scan":
        return shield.scan(args.path or Path.home())
    if args.action == "update":
        return shield.update()
    if args.action == "rootkit":
        return shield.rootkit_check()
    return shield.set_firewall(args.action == "firewall-on")


def cmd_vpn(args):
    try:
        if args.action == "list":
            for item in vpn.tunnels():
                print(f"{item['name']:20} {'connected' if item['active'] else 'off'}")
            return 0
        if args.action == "import":
            return vpn.import_config(args.value)
        if args.action in ("up", "down"):
            return vpn.switch(args.value, args.action == "up")
        folder = vpn.make_server(args.value, Path.home() / "moxwall")
        print(f"Created {folder}.\n1. Copy server-setup.sh to your server and run it as root.\n2. Delete that copy afterwards.\n3. Run: mox vpn import {folder}/moxwall.conf")
        return 0
    except vpn.VPNError as error:
        print(error, file=sys.stderr)
        return 1


def cmd_adblock(args):
    try:
        if args.action == "status":
            print(f"{adblock.blocked_count()} ad and tracker domains blocked")
        elif args.action == "on":
            flag = Path("/etc/mox/adblock-off")
            flag.unlink(missing_ok=True)
            print(f"Ad block is on. {adblock.update()} domains blocked.")
        elif args.action == "off":
            adblock.off()
            Path("/etc/mox/adblock-off").touch()
            print("Ad block is off.")
        else:
            adblock.allow(args.domain or "")
            print(f"Allowed {args.domain}.")
    except adblock.AdBlockError as error:
        print(error, file=sys.stderr)
        return 1
    return 0


def cmd_cloud(args):
    try:
        if args.action == "list":
            linked = cloud.connected()
            for service, (label, _backend) in cloud.REMOTES.items():
                print(f"{label:16} {'connected' if service in linked else 'not connected'}")
        elif args.action == "add":
            print(f"{cloud.add(args.service)} is in your Drives folder.")
        else:
            return cloud.remove(args.service)
    except cloud.CloudError as error:
        print(error, file=sys.stderr)
        return 1
    return 0


def cmd_optimize(args):
    if os.geteuid() != 0:
        extra = ["--mode", args.mode] if args.mode else []
        return subprocess.run(["pkexec", "mox", "optimize"] + extra, check=False).returncode
    settings = optimize.apply(auto=args.auto, mode=args.mode)
    if settings:
        print(optimize.describe(settings))
    return 0


def cmd_health(args):
    data = health.report()
    print(json.dumps(data, indent=2) if args.json else health.text(data))
    return 0


def cmd_wipe(args):
    try:
        if args.kind == "disk":
            return wipe.erase_disk(args.target)
        if args.kind == "keys":
            return wipe.erase_keys(args.target)
        print("Note: on an SSD, only full-disk encryption or 'mox wipe disk' is a reliable erase.")
        return wipe.shred_file(args.target)
    except wipe.WipeError as error:
        print(error, file=sys.stderr)
        return 1


def cmd_wifi(args):
    if args.action == "qr":
        return wifi.share_qr(args.name or "")
    if args.action == "ping":
        result = wifi.latency()
        print(f"Average {result['average_ms']} ms, jitter {result['jitter_ms']} ms, {result['loss_percent']}% lost" if result else "No reply. Check your connection.")
        return 0
    networks = wifi.scan()
    for network in sorted(networks, key=lambda n: -n["signal"]):
        print(f"{'*' if network['active'] else ' '} {network['ssid'][:28]:28} {network['signal']:3}%  ch {network['channel']:<3} {network['band']:7} {network['security']}")
    print()
    print("\n".join(wifi.advice(networks)))
    return 0


def cmd_fix(args):
    if not args.problem:
        for name, problem in fixer.PROBLEMS.items():
            print(f"{name:10} {problem['label']}")
        return 0
    if fixer.repair(args.problem):
        return 0
    print("\nAsking MOX AI. You'll approve any command before it runs.")
    try:
        return ai.fix(fixer.describe_for_ai(args.problem))
    except ai.AIError as error:
        print(error, file=sys.stderr)
        return 1


def cmd_power(args):
    display.apply_plan(args.plan)
    print(f"Power plan set to {args.plan}.")
    return 0


def cmd_theme(args):
    if not args.name:
        for name, theme in themes.THEMES.items():
            print(f"{name:10} {theme['label']}")
        return 0
    themes.apply(args.name)
    print(f"Theme set to {themes.THEMES[args.name]['label']}.")
    return 0


def cmd_wallpaper(args):
    if args.kind == "living":
        wallpaper.apply(wallpaper.LIVING)
        return 0
    try:
        title, credit = wallpaper.trending(args.kind)
    except (wallpaper.WallpaperError, OSError) as error:
        print(error, file=sys.stderr)
        return 1
    print(f"Wallpaper set: {title}\n{credit}")
    return 0


def cmd_mail(args):
    try:
        if args.action == "setup":
            if mail.has_identity():
                print("You already have a Quantum Mail key.")
            else:
                mail.create_identity()
                print(f"Created your post-quantum key in {mail.IDENTITY}")
                print("Back it up somewhere safe. Without it, mail sealed to you can't be opened.")
            return 0
        if args.action == "card":
            if not args.items:
                print("Usage: mox mail card YOUR@EMAIL [NAME]", file=sys.stderr)
                return 2
            print(mail.card(args.items[0], " ".join(args.items[1:])), end="")
            return 0
        if args.action == "add":
            text = Path(args.items[0]).read_text() if args.items else sys.stdin.read()
            contact = mail.read_card(text)
            print(f"Added {contact['name']}")
            return 0
        if args.action == "contacts":
            for email, info in sorted(mail.contacts().items()):
                print(f"{email:32} {info['name']}")
            return 0
        if args.action == "remove":
            mail.remove_contact(args.items[0])
            return 0
        if args.action == "seal":
            if not args.to:
                print("Choose who can open it: --to EMAIL", file=sys.stderr)
                return 2
            to = [x for x in args.to.split(",") if x]
            if args.items and Path(args.items[0]).is_file():
                if args.text:
                    print(mail.seal(Path(args.items[0]).read_text(), to), end="")
                else:
                    print(f"Sealed to {mail.seal_file(args.items[0], to)}")
                return 0
            print(mail.seal(sys.stdin.read(), to), end="")
            return 0
        if args.action == "open":
            if args.items and Path(args.items[0]).is_file() and not args.text:
                data = Path(args.items[0]).read_bytes()
                if b"BEGIN AGE ENCRYPTED FILE" not in data:
                    print(f"Opened to {mail.unseal_file(args.items[0])}")
                    return 0
                print(mail.unseal(data.decode(errors="replace")), end="")
                return 0
            print(mail.unseal(sys.stdin.read()), end="")
            return 0
        if args.action == "dns":
            if len(args.items) != 2:
                print("Usage: mox mail dns DOMAIN SERVER_IP", file=sys.stderr)
                return 2
            for kind, name, value in mail.dns_records(*args.items):
                print(f"{kind:4} {name:34} {value}")
            return 0
    except (mail.MailError, OSError) as error:
        print(error, file=sys.stderr)
        return 1
    return 0


def build_parser():
    parser = argparse.ArgumentParser(prog="mox", description="MOX system tools")
    parser.add_argument("--version", action="version", version=f"MOX {version()}")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("status", help="show compatibility layers and tools").set_defaults(func=cmd_status)
    item = sub.add_parser("hw", help="show hardware")
    item.add_argument("--json", action="store_true")
    item.set_defaults(func=cmd_hw)
    item = sub.add_parser("drivers", help="find and install drivers")
    item.add_argument("--install", action="store_true")
    item.add_argument("--ai", action="store_true", help="ask AI about devices with no driver")
    item.set_defaults(func=cmd_drivers)
    item = sub.add_parser("ai", help="ask MOX AI")
    item.add_argument("prompt", nargs="*")
    item.set_defaults(func=cmd_ai)
    item = sub.add_parser("get", help="install an add-on")
    item.add_argument("addon", nargs="?")
    item.set_defaults(func=cmd_get)
    item = sub.add_parser("update", help="install signed updates from the creator")
    item.add_argument("--check", action="store_true")
    item.add_argument("--url", help=argparse.SUPPRESS)
    item.set_defaults(func=cmd_update)
    item = sub.add_parser("sync", help="get the newest MOX from GitHub")
    item.add_argument("action", nargs="?", default="now", choices=["now", "on", "off", "status"])
    item.set_defaults(func=cmd_sync)
    item = sub.add_parser("secureboot", help="check or repair Secure Boot")
    item.add_argument("action", nargs="?", default="check", choices=["check", "fix", "mok"])
    item.add_argument("file", nargs="?")
    item.set_defaults(func=cmd_secureboot)
    item = sub.add_parser("tool", help="add open source tools from GitHub")
    item.add_argument("action", choices=["add", "list", "remove"])
    item.add_argument("name", nargs="?")
    item.add_argument("--yes", action="store_true")
    item.set_defaults(func=cmd_tool)
    sub.add_parser("apps", help="show which kinds of app work on this PC").set_defaults(func=cmd_apps)
    item = sub.add_parser("connect", help="manage AI connectors")
    item.add_argument("action", choices=["list", "add", "remove", "setup"])
    item.add_argument("name", nargs="?")
    item.add_argument("target", nargs="?")
    item.add_argument("--env", action="append")
    item.set_defaults(func=cmd_connect)
    sub.add_parser("modo", help="open Modo").set_defaults(func=cmd_modo)
    item = sub.add_parser("bot", help="talk to MOX Bot")
    item.add_argument("message", nargs="*")
    item.set_defaults(func=cmd_bot)
    item = sub.add_parser("api", help="manage all API keys in one place")
    item.add_argument("action", choices=["list", "add", "remove", "setup", "free"])
    item.add_argument("name", nargs="?")
    item.set_defaults(func=cmd_api)
    sub.add_parser("speed", help="test internet speed").set_defaults(func=cmd_speed)
    item = sub.add_parser("shield", help="firewall and antivirus")
    item.add_argument("action", choices=["status", "scan", "update", "rootkit", "firewall-on", "firewall-off"])
    item.add_argument("path", nargs="?")
    item.set_defaults(func=cmd_shield)
    item = sub.add_parser("vpn", help="MOXWALL VPN")
    item.add_argument("action", choices=["list", "import", "up", "down", "make-server"])
    item.add_argument("value", nargs="?")
    item.set_defaults(func=cmd_vpn)
    item = sub.add_parser("adblock", help="block ads and trackers everywhere")
    item.add_argument("action", choices=["status", "on", "off", "allow"])
    item.add_argument("domain", nargs="?")
    item.set_defaults(func=cmd_adblock)
    item = sub.add_parser("cloud", help="Google Drive and iCloud drives")
    item.add_argument("action", choices=["list", "add", "remove", "setup"])
    item.add_argument("service", nargs="?", choices=["google", "icloud"])
    item.set_defaults(func=cmd_cloud)
    item = sub.add_parser("optimize", help="tune MOX for this hardware")
    item.add_argument("--auto", action="store_true", help="only when hardware has changed")
    item.add_argument("--mode", choices=["auto", "lite", "full"], help="lite is fastest, full has every effect")
    item.set_defaults(func=cmd_optimize)
    item = sub.add_parser("health", help="report SSD and system health")
    item.add_argument("--json", action="store_true")
    item.set_defaults(func=cmd_health)
    item = sub.add_parser("wipe", help="permanently erase a file, drive or drive keys")
    item.add_argument("kind", choices=["file", "disk", "keys"])
    item.add_argument("target")
    item.set_defaults(func=cmd_wipe)
    item = sub.add_parser("wifi", help="check and improve your WiFi")
    item.add_argument("action", nargs="?", default="scan", choices=["scan", "ping", "qr"])
    item.add_argument("name", nargs="?", help="network name for qr")
    item.set_defaults(func=cmd_wifi)
    item = sub.add_parser("fix", help="troubleshoot and repair a problem")
    item.add_argument("problem", nargs="?", choices=sorted(fixer.PROBLEMS))
    item.set_defaults(func=cmd_fix)
    item = sub.add_parser("power", help="choose a power plan")
    item.add_argument("plan", choices=sorted(display.PLANS))
    item.set_defaults(func=cmd_power)
    item = sub.add_parser("theme", help="change the whole look")
    item.add_argument("name", nargs="?", choices=sorted(themes.THEMES))
    item.set_defaults(func=cmd_theme)
    item = sub.add_parser("wallpaper", help="set a wallpaper")
    item.add_argument("kind", choices=["living", "movie", "tv", "game"])
    item.set_defaults(func=cmd_wallpaper)
    item = sub.add_parser("mail", help="MOX Quantum Mail: post-quantum sealed email")
    item.add_argument("action", choices=["setup", "card", "add", "contacts", "remove", "seal", "open", "dns"])
    item.add_argument("items", nargs="*")
    item.add_argument("--to", help="emails or keys, separated by commas")
    item.add_argument("--text", action="store_true", help="treat the file as a message")
    item.set_defaults(func=cmd_mail)
    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return 0
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
