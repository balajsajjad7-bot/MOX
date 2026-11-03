import io, json, os, plistlib, shutil, struct, subprocess, sys, tarfile, tempfile, unittest, zipfile
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "overlay/usr/lib/mox"))
from moxos import tools, freeapis, addons, mail, cli, adblock, ai, bot, health, news, optimize, player, themes, wifi, wipe, fixer, display, cloud, drives, connectors, hardware, ipa, net, runner, shield, update, vault, vpn, wallpaper, widgets


def macho64(cpu=ipa.CPU_ARM64, cryptid=0):
    cmd = struct.pack("<IIIIIII", ipa.LC_ENCRYPTION_INFO_64, 24, 0, 0, cryptid, 0, 0)[:24]
    return struct.pack("<IIIIIIII", 0xFEEDFACF, cpu, 0, 2, 1, 24, 0, 0) + cmd


def macho32(cpu=ipa.CPU_ARM, cryptid=0):
    cmd = struct.pack("<IIIII", ipa.LC_ENCRYPTION_INFO, 20, 0, 0, cryptid)
    return struct.pack("<IIIIIII", 0xFEEDFACE, cpu, 0, 2, 1, 20, 0) + cmd


def make_ipa(path, binary, min_os="3.0"):
    info = {"CFBundleExecutable": "Game", "CFBundleName": "Game", "MinimumOSVersion": min_os}
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("Payload/Game.app/Info.plist", plistlib.dumps(info, fmt=plistlib.FMT_BINARY))
        archive.writestr("Payload/Game.app/Game", binary)


class Detect(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = Path(self.dir.name)

    def tearDown(self):
        self.dir.cleanup()

    def write(self, name, data):
        target = self.path / name
        target.write_bytes(data)
        return target

    def test_magic_beats_extension(self):
        self.assertEqual(runner.detect(self.write("setup.txt", b"MZ" + b"\0" * 100)), "windows")
        self.assertEqual(runner.detect(self.write("tool", b"\x7fELF\2\1\1" + b"\0" * 50)), "linux")
        self.assertEqual(runner.detect(self.write("a.bin", b"\x7fELF\2\1\1\0AI\x02" + b"\0" * 50)), "appimage")
        self.assertEqual(runner.detect(self.write("mac", b"\xcf\xfa\xed\xfe" + b"\0" * 50)), "mac")
        self.assertEqual(runner.detect(self.write("x.pkg", b"xar!" + b"\0" * 50)), "mac")
        self.assertEqual(runner.detect(self.write("run", b"#!/bin/sh\n")), "script")

    def test_archives(self):
        apk = self.path / "app.zip"
        with zipfile.ZipFile(apk, "w") as z:
            z.writestr("AndroidManifest.xml", "x")
        self.assertEqual(runner.detect(apk), "android")
        fake = self.path / "x.ipa"
        make_ipa(fake, macho64())
        self.assertEqual(runner.detect(fake), "iphone")

    def test_modern_ipa_is_refused_with_reason(self):
        fake = self.path / "x.ipa"
        make_ipa(fake, macho64(), "15.0")
        item = runner.plan(fake)
        self.assertIn("64-bit", item.problem)
        self.assertIn("Android", item.problem)
        self.assertEqual(item.command, [])

    def test_encrypted_old_ipa(self):
        fake = self.path / "x.ipa"
        make_ipa(fake, macho32(cryptid=1))
        self.assertIn("encrypted", ipa.inspect(fake).reason)

    def test_new_32bit_ipa(self):
        fake = self.path / "x.ipa"
        make_ipa(fake, macho32(), "6.0")
        self.assertIn("iOS 6.0", ipa.inspect(fake).reason)

    def test_old_ipa_supported(self):
        fake = self.path / "x.ipa"
        make_ipa(fake, macho32())
        report = ipa.inspect(fake)
        self.assertTrue(report.supported, report.reason)
        self.assertEqual(report.arches, ["armv7"])

    def test_fat_binary(self):
        one, two = macho32(), macho64()
        header = struct.pack(">II", 0xCAFEBABE, 2)
        first = 8 + 40
        header += struct.pack(">IIIII", ipa.CPU_ARM, 0, first, len(one), 0)
        header += struct.pack(">IIIII", ipa.CPU_ARM64, 0, first + len(one), len(two), 0)
        self.assertEqual([c for c, _ in ipa.macho_slices(header + one + two)], [ipa.CPU_ARM, ipa.CPU_ARM64])

    def test_broken_ipa_does_not_crash(self):
        self.assertFalse(ipa.inspect(self.write("bad.ipa", b"PKnope")).supported)

    def test_exe_plan_and_missing_addon(self):
        exe = self.write("a.exe", b"MZ\0\0")
        with mock.patch.object(runner, "have", return_value=False):
            item = runner.plan(exe)
        self.assertEqual((item.command[0], item.missing), ("wine", "windows"))

    def test_unknown_and_missing(self):
        self.assertTrue(runner.plan(self.write("note.xyz", b"hello")).problem)
        self.assertTrue(runner.plan(self.path / "gone.exe").problem)


class Hardware(unittest.TestCase):
    SAMPLE = """00:02.0 VGA compatible controller [0300]: Intel Corporation UHD Graphics [8086:9bc4]
\tSubsystem: Dell Device [1028:0a0e]
\tKernel driver in use: i915
\tKernel modules: i915
02:00.0 Network controller [0280]: Broadcom BCM4360 [14e4:43a0]
\tSubsystem: Apple Inc. Device [106b:0112]
"""

    def test_lspci(self):
        devices = hardware.parse_lspci_k(self.SAMPLE)
        self.assertEqual(devices[0]["driver"], "i915")
        self.assertEqual(devices[1]["driver"], "")
        self.assertEqual(devices[1]["class"], "Network controller")

    def test_ubuntu_drivers(self):
        text = "nvidia-driver-580, (kernel modules provided by linux-modules-nvidia)\nbcmwl-kernel-source\nUDI: x\n"
        self.assertEqual(hardware.parse_ubuntu_drivers(text), ["nvidia-driver-580", "bcmwl-kernel-source"])


class AI(unittest.TestCase):
    def test_blocks(self):
        self.assertEqual(ai.command_blocks("hi\n```bash\nls\n```\n```python\nx\n```"), ["ls"])

    def test_fix_never_runs_without_consent(self):
        with mock.patch.object(ai, "ask", return_value="```bash\ntouch /tmp/moxbad\n```"), \
             mock.patch.object(ai, "confirm", return_value=False), \
             mock.patch.object(ai.subprocess, "run") as execute, \
             mock.patch.object(ai.hardware, "summary", return_value={"cpu": "", "cores": 1, "memory_gb": 1, "kernel": "", "disks": [], "pci": [], "available_drivers": [], "missing_drivers": []}), \
             mock.patch("builtins.print"):
            ai.fix("test")
        execute.assert_not_called()

    def test_keys_are_private(self):
        with tempfile.TemporaryDirectory() as folder, mock.patch.object(vault, "STORE", Path(folder) / "k.json"), mock.patch.object(vault, "ENV_FILE", Path(folder) / "e.env"), mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": ""}):
            ai.set_key("anthropic", "secret")
            self.assertEqual(ai.get_key("anthropic"), "secret")
            self.assertEqual(os.stat(vault.STORE).st_mode & 0o777, 0o600)
            self.assertEqual(os.stat(vault.ENV_FILE).st_mode & 0o777, 0o600)


class Vault(unittest.TestCase):
    def test_vault(self):
        with tempfile.TemporaryDirectory() as folder, mock.patch.object(vault, "STORE", Path(folder) / "k.json"), mock.patch.object(vault, "ENV_FILE", Path(folder) / "e.env"):
            self.assertEqual(vault.add("my-key", "ab'c def"), "MY_KEY")
            shell = subprocess.run(["bash", "-c", f". {vault.ENV_FILE}; printf %s \"$MY_KEY\""], capture_output=True, text=True).stdout
            self.assertEqual(shell, "ab'c def")
            with self.assertRaises(ValueError):
                vault.add("1;rm -rf", "x")
            self.assertNotIn("abcdef", str(vault.masked()))
            self.assertTrue(vault.remove("MY_KEY"))


class Net(unittest.TestCase):
    def test_interface_bytes(self):
        text = "h1\nh2\n lo: 9 0 0 0 0 0 0 0 9 0\n eth0: 100 0 0 0 0 0 0 0 50 0\n docker0: 7 0 0 0 0 0 0 0 7 0\n"
        self.assertEqual(net.interface_bytes(text), (100, 50))

    def test_rate(self):
        self.assertEqual(net.human_rate(125000), "1.0 Mbps")
        self.assertEqual(net.human_rate(1250), "10 Kbps")

    def test_threats(self):
        items = [{"status": "online", "malware": "Emotet", "country": "US"}, {"status": "online", "malware": "Emotet", "country": "DE"}, {"status": "offline", "malware": "QakBot", "country": "RU"}]
        self.assertEqual(net.summarize_botnets(items)["active"], 2)
        self.assertEqual(net.summarize_botnets(items)["top_family"], "Emotet")
        feed = {"vulnerabilities": [{"cveID": "CVE-1", "dateAdded": "2026-01-01", "vendorProject": "A", "product": "B"}, {"cveID": "CVE-2", "dateAdded": "2026-02-01", "vendorProject": "C", "product": "D"}]}
        self.assertEqual(net.latest_exploit(feed), "CVE-2: C D")

    def test_feed_down_is_shown_honestly(self):
        out = widgets.compose((0, 0), {}, None, 0)
        self.assertFalse(out["feed_ok"])
        self.assertEqual(out["speed"], "Run: mox speed")


class VPN(unittest.TestCase):
    def test_files(self):
        script, client = vpn.server_files("203.0.113.9", keys=("sp", "sP", "cp", "cP", "psk"))
        self.assertIn("PrivateKey = sp", script)
        self.assertIn("PublicKey = cP", script)
        self.assertIn("Endpoint = 203.0.113.9:51820", client)
        self.assertIn("moxwall0", script)
        self.assertIn("PresharedKey = psk", script)
        self.assertIn("PresharedKey = psk", client)
        self.assertIn("PublicKey = sP", client)
        self.assertNotIn("sp\n", client)

    def test_bad_host(self):
        with self.assertRaises(vpn.VPNError):
            vpn.server_files("x; rm -rf /", keys=("a", "b", "c", "d", "e"))


class Bot(unittest.TestCase):
    def test_local_answers_never_use_ai(self):
        with mock.patch.object(bot.ai, "ask") as ask:
            self.assertIn("MOX Bot", bot.reply("hello"))
            ask.assert_not_called()

    def test_falls_back_to_help(self):
        with mock.patch.object(bot.ai, "ask", side_effect=ai.AIError("No AI is set up.")):
            self.assertIn("No AI", bot.reply("write me a poem"))


class Shield(unittest.TestCase):
    def test_firewall_flag(self):
        with tempfile.TemporaryDirectory() as folder:
            conf = Path(folder) / "ufw.conf"
            conf.write_text("ENABLED=yes\n")
            self.assertTrue(shield.firewall_enabled(conf))
            conf.write_text("ENABLED=no\n")
            self.assertFalse(shield.firewall_enabled(conf))


class AdBlock(unittest.TestCase):
    LIST = "127.0.0.1 localhost\n0.0.0.0 0.0.0.0\n0.0.0.0 ads.example.com # x\n0.0.0.0 track.example.net\n1.2.3.4 bank.example.com\n0.0.0.0 bad domain\n"

    def test_parse_only_blocks(self):
        self.assertEqual(adblock.parse(self.LIST), ["ads.example.com", "track.example.net"])

    def test_allow(self):
        self.assertEqual(adblock.parse(self.LIST, ["ads.example.com"]), ["track.example.net"])

    def test_merge_is_repeatable_and_keeps_hosts(self):
        base = "127.0.0.1 localhost\n"
        once = adblock.merged(base, ["a.example.com"])
        twice = adblock.merged(once, ["b.example.com"])
        self.assertIn("127.0.0.1 localhost", twice)
        self.assertIn("b.example.com", twice)
        self.assertNotIn("a.example.com", twice)
        self.assertEqual(adblock.strip_block(twice).strip(), base.strip())


class Cloud(unittest.TestCase):
    def test_version(self):
        self.assertEqual(cloud.rclone_version("rclone v1.71.2\n- os"), (1, 71))
        self.assertEqual(cloud.rclone_version(""), (0, 0))
        self.assertLess(cloud.rclone_version("rclone 1.60.1-DEV"), (1, 69))

    def test_unknown(self):
        with self.assertRaises(cloud.CloudError):
            cloud.add("dropbox")


class Drives(unittest.TestCase):
    def test_parse(self):
        data = {"blockdevices": [
            {"name": "sda", "type": "disk", "rm": False, "hotplug": False, "children": [
                {"name": "sda1", "path": "/dev/sda1", "type": "part", "fstype": "vfat", "mountpoint": "/boot/efi", "size": 500},
                {"name": "sda2", "path": "/dev/sda2", "type": "part", "fstype": "ext4", "mountpoint": "/", "size": 1000 * 1024 ** 3, "fsused": 250 * 1024 ** 3, "fsavail": 750 * 1024 ** 3},
                {"name": "sda3", "path": "/dev/sda3", "type": "part", "fstype": "swap", "size": 10}]},
            {"name": "sdb", "type": "disk", "rm": True, "children": [
                {"name": "sdb1", "path": "/dev/sdb1", "type": "part", "fstype": "exfat", "label": "USB", "size": 2048}]}]}
        items = drives.parse(json.dumps(data))
        self.assertEqual([item["name"] for item in items], ["This PC", "USB"])
        self.assertEqual(items[0]["fraction"], 0.25)
        self.assertTrue(items[1]["removable"])
        self.assertIn("not opened", items[1]["text"])


class News(unittest.TestCase):
    def test_rss_and_atom(self):
        rss = "<rss><channel><item><title>A</title><link>https://x.test/a</link></item><item><title>B</title><link>javascript:evil</link></item></channel></rss>"
        self.assertEqual(news.parse(rss), [{"title": "A", "link": "https://x.test/a"}])
        atom = '<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>C</title><link href="https://x.test/c"/></entry></feed>'
        self.assertEqual(news.parse(atom)[0]["title"], "C")


class Themes(unittest.TestCase):
    def test_every_wallpaper_exists(self):
        folder = REPO / "overlay/usr/share/backgrounds/mox"
        for theme in themes.THEMES.values():
            self.assertTrue((folder / theme["wallpaper"]).exists(), theme["wallpaper"])

    def test_css_merge_keeps_user_css(self):
        one = themes.merge_css("a { }\n", themes.app_css(0.7))
        two = themes.merge_css(one, themes.app_css(0.9))
        self.assertIn("a { }", two)
        self.assertIn("0.9", two)
        self.assertNotIn("0.7", two)
        self.assertEqual(two.count(themes.START), 1)
        self.assertEqual(themes.merge_css(two, themes.app_css(1)).strip(), "a { }")


class Optimizer(unittest.TestCase):
    def test_small_laptop_with_hard_disk(self):
        out = optimize.plan({"memory_gb": 4, "cores": 4, "disks": [{"name": "sda", "kind": "hdd"}], "laptop": True})
        self.assertEqual(out["sysctl"]["vm.swappiness"], 150)
        self.assertFalse(out["trim"])
        self.assertEqual(out["power"], "balanced")

    def test_big_nvme_desktop(self):
        out = optimize.plan({"memory_gb": 64, "cores": 24, "disks": [{"name": "nvme0n1", "kind": "nvme"}], "laptop": False})
        self.assertEqual(out["sysctl"]["vm.swappiness"], 30)
        self.assertEqual(out["zram_mb"], 16384)
        self.assertTrue(out["trim"])
        self.assertEqual(out["build_jobs"], 24)
        files = optimize.render(out)
        self.assertIn("-j24", files[optimize.PROFILE])

    def test_auto_skips_when_unchanged(self):
        with tempfile.TemporaryDirectory() as folder:
            stamp = Path(folder) / "s.json"
            box = {"memory_gb": 8, "cores": 2, "disks": [], "laptop": False}
            stamp.write_text(json.dumps({"hardware": optimize.fingerprint(box)}))
            with mock.patch.object(optimize, "STAMP", stamp), mock.patch.object(optimize, "detect", return_value=box), mock.patch.object(optimize, "render") as render:
                self.assertIsNone(optimize.apply(auto=True))
                render.assert_not_called()


class Health(unittest.TestCase):
    def test_nvme(self):
        data = {"model_name": "NVMe X", "smart_status": {"passed": True}, "temperature": {"current": 41}, "power_on_time": {"hours": 900},
                "nvme_smart_health_information_log": {"percentage_used": 7, "available_spare": 100, "media_errors": 0}}
        disk = health.read_smart(data)
        self.assertEqual((disk["wear_percent"], health.verdict(disk)), (7, "Healthy"))

    def test_failing(self):
        data = {"smart_status": {"passed": True}, "ata_smart_attributes": {"table": [{"name": "Reallocated_Sector_Ct", "value": 90, "raw": {"value": 12}}]}}
        self.assertIn("Failing", health.verdict(health.read_smart(data)))

    def test_unknown_is_not_called_healthy(self):
        self.assertEqual(health.verdict(health.read_smart({})), "Unknown")

    def test_worn(self):
        disk = health.read_smart({"smart_status": {"passed": True}, "nvme_smart_health_information_log": {"percentage_used": 95}})
        self.assertIn("Worn", health.verdict(disk))

    def test_cpu_temp(self):
        self.assertEqual(health.hottest_cpu(json.dumps({"coretemp": {"Core 0": {"temp2_input": 51.0}, "Core 1": {"temp3_input": 63.4}}, "Adapter": "x"})), 63)


class Wipe(unittest.TestCase):
    def test_system_disk_is_protected(self):
        data = {"blockdevices": [{"name": "sda", "children": [{"name": "sda1", "mountpoint": "/"}]}, {"name": "sdb", "children": [{"name": "sdb1", "mountpoint": "/mnt/x"}]}]}
        self.assertEqual(wipe.system_disks(json.dumps(data)), {"sda"})

    def test_erase_refuses_system_disk(self):
        with mock.patch.object(wipe.os, "geteuid", return_value=0), mock.patch.object(wipe, "system_disks", return_value={"sda"}):
            with self.assertRaises(wipe.WipeError):
                wipe.erase_disk("sda")

    def test_no_erase_without_consent(self):
        with mock.patch.object(wipe.os, "geteuid", return_value=0), mock.patch.object(wipe, "system_disks", return_value=set()), \
             mock.patch.object(wipe, "confirm", return_value=False), mock.patch.object(wipe.subprocess, "run") as execute:
            self.assertEqual(wipe.erase_disk("sdb"), 1)
        execute.assert_not_called()

    def test_nvme_plan(self):
        self.assertEqual(wipe.plan("nvme0n1")[0][:2], ["nvme", "format"])


class WiFi(unittest.TestCase):
    def test_signal(self):
        out = wifi.parse_signal("yes:HomeNet:82:6:270 Mbit/s\nno:Other:40:11")
        self.assertEqual((out["ssid"], out["signal"], out["channel"]), ("HomeNet", 82, "6"))

    def test_channel_load(self):
        nets = wifi.parse_networks("no:A:70:6\nno:B:50:6\nno:C:40:11\nno::10:1")
        self.assertEqual([n["ssid"] for n in nets], ["A", "B", "C"])
        self.assertEqual(wifi.channel_load(nets)["6"], 2)

    def test_quality(self):
        self.assertEqual(wifi.quality_word(80), "Excellent")
        self.assertEqual(wifi.quality_word(20), "Very weak")


class Player(unittest.TestCase):
    def test_routes(self):
        self.assertEqual(player.route("a.mp4", "video/mp4")[0], "mpv")
        self.assertEqual(player.route("a.mp5", "application/octet-stream")[0], "mpv")
        self.assertEqual(player.route("a.pdf", "application/pdf")[0], "papers")
        self.assertEqual(player.route("a.docx", "application/zip")[0], "libreoffice")
        self.assertEqual(player.route("a.png", "image/png")[0], "loupe")
        self.assertEqual(player.route("a.7z", "application/x-7z-compressed")[0], "file-roller")
        self.assertEqual(player.route("a.exe", "application/x-dosexec")[0], "mox-run")
        self.assertEqual(player.route("a.xyz", "application/octet-stream"), [])

    def test_scripts_are_not_run_by_opening(self):
        self.assertEqual(player.route("a.sh", "text/x-shellscript")[0], "gnome-text-editor")


class WiFi(unittest.TestCase):
    SCAN = "*:Home:6:42:WPA2:2437 MHz\n :Home:44:70:WPA2:5220 MHz\n :Cafe\\:Free:1:80:WPA2:2412 MHz\n :Shop:6:75:WPA2:2437 MHz\n :Old:11:20::2462 MHz\n"

    def test_parse(self):
        nets = wifi.parse_scan(self.SCAN)
        self.assertEqual(len(nets), 5)
        self.assertEqual(nets[2]["ssid"], "Cafe:Free")
        self.assertEqual(nets[1]["band"], "5 GHz")
        self.assertEqual(nets[4]["security"], "Open")

    def test_channel_and_advice(self):
        nets = wifi.parse_scan(self.SCAN)
        self.assertEqual(wifi.best_channel(nets), 11)
        tips = " ".join(wifi.advice(nets))
        self.assertIn("Channel 11", tips)
        self.assertIn("5 GHz", tips)


class Downloader(unittest.TestCase):
    def test_progress(self):
        from importlib import import_module
        sys.modules.setdefault("gi", mock.MagicMock()); sys.modules.setdefault("gi.repository", mock.MagicMock())
        downloads = import_module("moxos.downloads")
        info = downloads.parse_progress("[#2089b0 12MiB/100MiB(12%) CN:8 DL:5.1MiB ETA:17s]")
        self.assertEqual((info["percent"], info["speed"], info["eta"]), (12, "5.1MiB/s", "17s"))
        with self.assertRaises(ValueError):
            downloads.command("file:///etc/passwd")


class Fixer(unittest.TestCase):
    def test_every_problem_is_safe(self):
        banned = ("rm", "mkfs", "dd", "shred", "ufw", "chmod", "chown")
        for problem in fixer.PROBLEMS.values():
            for _label, command in problem["fixes"] + problem.get("user_fixes", []):
                self.assertNotIn(command[0], banned)

    def test_stops_when_fixed(self):
        with mock.patch.object(fixer, "is_fixed", side_effect=[False, True]), mock.patch.object(fixer, "have", return_value=True), \
             mock.patch.object(fixer.os, "geteuid", return_value=0), mock.patch.object(fixer.subprocess, "run") as execute:
            self.assertTrue(fixer.repair("internet", log=lambda *_: None))
        self.assertEqual(execute.call_count, 1)


class Power(unittest.TestCase):
    def test_plans(self):
        with mock.patch.object(display, "have", return_value=True):
            commands = display.plan_commands("performance")
        self.assertIn(["gsettings", "set", "org.gnome.settings-daemon.plugins.power", "sleep-inactive-ac-type", "nothing"], commands)
        self.assertEqual(commands[-1], ["powerprofilesctl", "set", "performance"])


class Rollout(unittest.TestCase):
    def test_rules(self):
        with mock.patch.object(update, "version", return_value="0.1.0"):
            self.assertTrue(update.wanted({"version": "0.2.0"}, bucket=99))
            self.assertFalse(update.wanted({"version": "0.2.0", "paused": True}, bucket=0))
            self.assertFalse(update.wanted({"version": "0.2.0", "rollout": 10}, bucket=50))
            self.assertTrue(update.wanted({"version": "0.2.0", "rollout": 10}, bucket=5))
            self.assertFalse(update.wanted({"version": "0.1.0"}, bucket=0))

    def test_bucket_is_stable(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "id"
            path.write_text("abc\n")
            self.assertEqual(update.machine_bucket(path), update.machine_bucket(path))


class Wallpaper(unittest.TestCase):
    def test_needs_key(self):
        with mock.patch.object(wallpaper.vault, "get", return_value=""):
            with self.assertRaises(wallpaper.WallpaperError):
                wallpaper.trending("movie")

    def test_pick(self):
        self.assertEqual(wallpaper.pick_title([{"title": "a"}, {"title": "b", "backdrop_path": "/x.jpg"}])["title"], "b")


class Connectors(unittest.TestCase):
    def test_roundtrip(self):
        with tempfile.TemporaryDirectory() as folder, mock.patch.object(connectors, "FILE", Path(folder) / "m.json"):
            connectors.add("web", "https://example.com/mcp")
            connectors.add("db", "npx server --port 1", ["A=b"])
            data = connectors.load()["mcpServers"]
            self.assertEqual(data["web"]["type"], "http")
            self.assertEqual(data["db"], {"command": "npx", "args": ["server", "--port", "1"], "env": {"A": "b"}})
            self.assertTrue(connectors.remove("web"))
            self.assertFalse(connectors.remove("web"))


class Updates(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.base = Path(self.dir.name)
        self.key = self.base / "creator.key"
        self.pub = self.base / "creator.pub"
        subprocess.run(["openssl", "genpkey", "-algorithm", "ED25519", "-out", self.key], check=True, capture_output=True)
        subprocess.run(["openssl", "pkey", "-in", self.key, "-pubout", "-out", self.pub], check=True, capture_output=True)
        self.root = self.base / "root"
        (self.root / "usr/lib/mox").mkdir(parents=True)
        (self.root / "usr/lib/mox/VERSION").write_text("0.1.0\n")
        patches = [
            mock.patch.object(update, "PUBKEY", self.pub),
            mock.patch.object(update, "ROOT", self.root),
            mock.patch.object(update, "VERSION_FILE", self.root / "usr/lib/mox/VERSION"),
            mock.patch.object(update, "version", lambda: (self.root / "usr/lib/mox/VERSION").read_text().strip()),
            mock.patch.object(update.verify_signature, "__defaults__", (self.pub,)),
        ]
        for item in patches:
            item.start()
            self.addCleanup(item.stop)

    def tearDown(self):
        self.dir.cleanup()

    def release(self, version, key=None):
        payload = self.base / f"p{version}"
        (payload / "rootfs/usr/share/mox").mkdir(parents=True)
        (payload / "rootfs/usr/share/mox/hello").write_text(version)
        out = self.base / f"d{version}"
        env = dict(os.environ, MOX_KEY=str(key or self.key))
        subprocess.run([REPO / "tools/mox-release", version, payload, out], check=True, capture_output=True, env=env)
        return out, f"file://{out}/manifest.json"

    def test_good_update(self):
        _, url = self.release("0.2.0")
        self.assertEqual(update.check(url)["version"], "0.2.0")
        with mock.patch.object(update, "healthy"):
            self.assertEqual(update.apply(url), "0.2.0")
        self.assertEqual((self.root / "usr/share/mox/hello").read_text(), "0.2.0")
        self.assertEqual((self.root / "usr/lib/mox/VERSION").read_text().strip(), "0.2.0")

    def test_broken_update_rolls_back(self):
        code = self.root / "usr/lib/mox/moxos"
        code.mkdir()
        (code / "keep.py").write_text("old")
        _, url = self.release("0.2.0")
        with mock.patch.object(update, "healthy", side_effect=subprocess.CalledProcessError(1, "x")):
            with self.assertRaises(update.UpdateError):
                update.apply(url)
        self.assertEqual((code / "keep.py").read_text(), "old")
        self.assertEqual((self.root / "usr/lib/mox/VERSION").read_text().strip(), "0.1.0")

    def test_other_key_rejected(self):
        other = self.base / "other.key"
        subprocess.run(["openssl", "genpkey", "-algorithm", "ED25519", "-out", other], check=True, capture_output=True)
        _, url = self.release("0.2.0", other)
        with self.assertRaises(update.UpdateError):
            update.apply(url)
        self.assertFalse((self.root / "usr/share/mox/hello").exists())

    def test_tampered_manifest_rejected(self):
        out, url = self.release("0.2.0")
        data = json.loads((out / "manifest.json").read_text())
        data["version"] = "9.9.9"
        (out / "manifest.json").write_text(json.dumps(data))
        with self.assertRaises(update.UpdateError):
            update.check(url)

    def test_tampered_archive_rejected(self):
        out, url = self.release("0.2.0")
        with open(out / "mox-0.2.0.tar.gz", "ab") as handle:
            handle.write(b"evil")
        with self.assertRaises(update.UpdateError):
            update.apply(url)

    def test_downgrade_ignored(self):
        _, url = self.release("0.0.9")
        self.assertIsNone(update.check(url))
        self.assertIsNone(update.apply(url))

    def test_path_escape_blocked(self):
        archive = self.base / "evil.tar.gz"
        with tarfile.open(archive, "w:gz") as bundle:
            info = tarfile.TarInfo("../escaped")
            info.size = 1
            bundle.addfile(info, io.BytesIO(b"x"))
        target = self.base / "t"
        target.mkdir()
        with self.assertRaises(tarfile.TarError):
            update._safe_extract(archive, target)


class GithubTools(unittest.TestCase):
    def test_accepts_short_names_and_links(self):
        self.assertEqual(tools.parse("sharkdp/fd"), ("sharkdp", "fd"))
        self.assertEqual(tools.parse("https://github.com/sharkdp/fd.git"), ("sharkdp", "fd"))

    def test_refuses_other_sites_and_tricks(self):
        for bad in ("https://evil.example/a/b", "a/b;rm -rf ~", "../x"):
            with self.assertRaises(tools.ToolError):
                tools.parse(bad)

    def test_detects_project_type(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)
            self.assertEqual(tools.kind(path), "files")
            (path / "go.mod").write_text("module x")
            self.assertEqual(tools.kind(path), "go")
            (path / "requirements.txt").write_text("")
            self.assertEqual(tools.kind(path), "python")


class Sync(unittest.TestCase):
    def repo(self, base, broken=False):
        source = base / "origin"
        shutil.copytree(REPO / "overlay/usr/lib/mox/moxos", source / "overlay/usr/lib/mox/moxos")
        for folder in ("overlay/etc/xdg/x", "overlay/etc/apt/apt.conf.d", "overlay/etc/dconf/db/local.d", "dialer"):
            (source / folder).mkdir(parents=True, exist_ok=True)
        (source / "overlay/etc/dconf/db/local.d/00-mox").write_text("x")
        (source / "overlay/etc/apt/apt.conf.d/a").write_text("x")
        (source / "dialer/d").write_text("x")
        (source / "overlay/etc/xdg/x/f").write_text("x")
        if broken:
            (source / "overlay/usr/lib/mox/moxos/cli.py").write_text("this is not python")
        git = ["git", "-c", "user.name=t", "-c", "user.email=t@t", "-C", str(source)]
        subprocess.run(["git", "init", "-q", "-b", "main", str(source)], check=True)
        subprocess.run(git + ["add", "-A"], check=True)
        subprocess.run(git + ["commit", "-qm", "x"], check=True)
        return source

    def run_sync(self, base, source):
        root = base / "root"
        (root / "usr/lib/mox").mkdir(parents=True, exist_ok=True)
        (root / "usr/lib/mox/old").write_text("old")
        env = dict(os.environ, MOX_SYNC_ROOT=str(root), MOX_SYNC_REPO=f"file://{source}")
        return root, subprocess.run(["bash", str(REPO / "overlay/usr/lib/mox/sync.sh")], env=env, capture_output=True, text=True)

    def test_installs_then_says_up_to_date(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            source = self.repo(base)
            root, done = self.run_sync(base, source)
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertTrue((root / "usr/lib/mox/moxos/cli.py").exists())
            self.assertIn("up to date", self.run_sync(base, source)[1].stdout)

    def test_bad_version_is_never_installed(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            root, done = self.run_sync(base, self.repo(base, broken=True))
            self.assertNotEqual(done.returncode, 0)
            self.assertFalse((root / "usr/lib/mox/moxos").exists())


class StarterConnectors(unittest.TestCase):
    def test_setup_keeps_your_own_and_adds_the_rest_once(self):
        with tempfile.TemporaryDirectory() as folder, mock.patch.object(connectors, "FILE", Path(folder) / "mcp.json"), mock.patch.object(connectors.Path, "home", return_value=Path(folder)):
            connectors.add("files", "my-own-tool")
            added = connectors.setup()
            self.assertNotIn("files", added)
            self.assertEqual(connectors.load()["mcpServers"]["files"]["command"], "my-own-tool")
            self.assertIn("memory", added)
            self.assertEqual(connectors.setup(), [])


class AddonState(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)

    def test_tool_on_path_counts_as_installed(self):
        with mock.patch.object(addons.shutil, "which", return_value="/usr/bin/wine"):
            self.assertTrue(addons.is_installed("windows"))
        with mock.patch.object(addons.shutil, "which", return_value=None):
            self.assertFalse(addons.is_installed("windows"))

    def test_android_needs_its_system_image(self):
        with mock.patch.object(addons.shutil, "which", return_value="/usr/bin/waydroid"), mock.patch.object(addons, "CHECKS", {"android": ["waydroid", self.dir.name + "/missing.img"]}):
            self.assertFalse(addons.is_installed("android"))

    def test_every_addon_has_a_way_to_tell(self):
        marked = {"quantum-mail", "chat"} | set(addons.CHECKS) | set(addons.FLATPAKS)
        self.assertEqual(set(addons.ADDONS) - marked, set())

    def test_failed_install_leaves_no_mark(self):
        marks = Path(self.dir.name) / "m"
        with mock.patch.object(addons, "MARKS", marks), mock.patch.object(addons.os, "geteuid", return_value=0), mock.patch.dict(addons.ADDONS, {"x": ("X", "exit 1"), "y": ("Y", "true")}):
            addons.install("x")
            self.assertFalse((marks / "x").exists())
            addons.install("y")
            self.assertTrue((marks / "y").exists())


class LiteMode(unittest.TestCase):
    small = {"memory_gb": 4.0, "cores": 2, "disks": [{"name": "sda", "kind": "hdd"}], "laptop": True}
    big = {"memory_gb": 32.0, "cores": 16, "disks": [{"name": "nvme0n1", "kind": "nvme"}], "laptop": False}

    def test_small_pc_gets_lite(self):
        settings = optimize.plan(self.small)
        self.assertTrue(settings["lite"])
        self.assertNotIn("blur-my-shell", optimize.render(settings)[optimize.LITE_DCONF])

    def test_big_pc_keeps_effects(self):
        settings = optimize.plan(self.big)
        self.assertFalse(settings["lite"])
        self.assertNotIn(optimize.LITE_DCONF, optimize.render(settings))

    def test_user_choice_wins(self):
        self.assertFalse(optimize.plan(self.small, "full")["lite"])
        self.assertTrue(optimize.plan(self.big, "lite")["lite"])


class QuantumMail(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        base = Path(self.dir.name)
        patches = [mock.patch.object(mail, "MAIL_DIR", base), mock.patch.object(mail, "IDENTITY", base / "identity.txt"),
                   mock.patch.object(mail, "CONTACTS", base / "contacts.json")]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        self.addCleanup(self.dir.cleanup)
        self.base = base

    def test_cli_parser_has_unique_commands(self):
        args = cli.build_parser().parse_args(["mail", "seal", "--to", "a@b.co"])
        self.assertEqual(args.to, "a@b.co")
        self.assertEqual(cli.build_parser().parse_args(["wifi", "ping"]).action, "ping")

    def test_classic_keys_refused(self):
        with self.assertRaises(mail.MailError):
            mail.check_key("age1" + "q" * 58)
        with self.assertRaises(mail.MailError):
            mail.add_contact("not-an-email", "age1pq1" + "q" * 1900)

    def test_card_round_trip_with_quoting(self):
        key = "age1pq1" + "q" * 1950
        with mock.patch.object(mail, "my_key", return_value=key):
            text = mail.card("me@mox.dev", "Me")
        quoted = "> " + text.replace("\n", "\n> ")
        contact = mail.read_card("Hi, here is my key\n" + quoted)
        self.assertEqual(contact["key"], key)
        self.assertEqual(oct(os.stat(mail.CONTACTS).st_mode & 0o777), "0o600")

    def test_unknown_email_needs_contact(self):
        with self.assertRaisesRegex(mail.MailError, "contact first"):
            mail._recipients(["stranger@x.io"])

    def test_dns_records(self):
        records = mail.dns_records("Modo.io", "203.0.113.5")
        self.assertIn(("MX", "modo.io", "10 mail.modo.io"), records)
        with self.assertRaises(mail.MailError):
            mail.dns_records("modo.io", "not-ip")

    def test_never_overwrites(self):
        (self.base / "a.txt").write_text("1")
        self.assertEqual(mail._free(self.base / "a.txt").name, "a (2).txt")

    @unittest.skipUnless(mail.pq_ready(), "age 1.3 not installed")
    def test_post_quantum_seal_and_open(self):
        mail.create_identity()
        bob = self.base / "bob.txt"
        subprocess.run([mail._tool("age-keygen"), "-pq", "-o", str(bob)], check=True, capture_output=True)
        bob_key = subprocess.run([mail._tool("age-keygen"), "-y", str(bob)], check=True, capture_output=True, text=True).stdout
        mail.add_contact("bob@mox.dev", bob_key, "Bob")
        sealed = mail.seal("meet at 9", ["bob@mox.dev"])
        self.assertNotIn("meet at 9", sealed)
        header = __import__("base64").b64decode("".join(sealed.split("-----")[2].split()[:2])[:64] + "==")
        self.assertIn(b"mlkem768x25519", header)
        opened = subprocess.run([mail._tool("age"), "-d", "-i", str(bob)], input=mail.ARMOR.search(sealed).group(0).encode(),
                                capture_output=True, check=True).stdout
        self.assertEqual(opened, b"meet at 9")
        self.assertEqual(mail.unseal("> " + sealed.replace("\n", "\n> ")), "meet at 9")
        stranger = self.base / "eve.txt"
        subprocess.run([mail._tool("age-keygen"), "-pq", "-o", str(stranger)], check=True, capture_output=True)
        with mock.patch.object(mail, "IDENTITY", stranger), self.assertRaisesRegex(mail.MailError, "wasn't sealed"):
            mail.unseal(sealed)
        source = self.base / "photo.jpg"
        source.write_bytes(os.urandom(5000))
        sealed_file = mail.seal_file(source, ["bob@mox.dev"])
        self.assertEqual(mail.unseal_file(sealed_file).read_bytes(), source.read_bytes())


if __name__ == "__main__":
    unittest.main()
