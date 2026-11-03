"""Optional add-ons that are too large, or too new, to ship in the ISO."""
import os
import shutil
import subprocess
from pathlib import Path

ADDONS = {
    "android": ("Android apps (Waydroid)", """
if ! command -v waydroid >/dev/null; then
  apt-get install -y curl ca-certificates lxc
  curl -fsS https://repo.waydro.id -o /tmp/waydroid-repo.sh
  bash /tmp/waydroid-repo.sh || bash /tmp/waydroid-repo.sh -s noble
  apt-get install -y waydroid
fi
modprobe binder_linux || true
echo binder_linux > /etc/modules-load.d/mox-android.conf
[ -f /var/lib/waydroid/images/system.img ] || waydroid init
if lspci | grep -i vga | grep -qi nvidia; then
  # Waydroid can't use NVIDIA's driver, so Android draws with the CPU on these PCs
  grep -q swiftshader /var/lib/waydroid/waydroid_base.prop 2>/dev/null || cat >> /var/lib/waydroid/waydroid_base.prop <<PROP
ro.hardware.gralloc=default
ro.hardware.egl=swiftshader
PROP
fi
systemctl enable --now waydroid-container
mox get android-arm || echo "ARM app support wasn't added. x86 apps still work."
"""),
    "android-arm": ("Run ARM-only Android apps on this PC", """
apt-get install -y git python3-venv lzip
rm -rf /opt/mox/src/waydroid_script && mkdir -p /opt/mox/src
git clone --depth 1 https://github.com/casualsnek/waydroid_script /opt/mox/src/waydroid_script
cd /opt/mox/src/waydroid_script
python3 -m venv venv
venv/bin/pip install -r requirements.txt
if grep -q GenuineIntel /proc/cpuinfo; then layer=libhoudini; else layer=libndk; fi
venv/bin/python main.py install "$layer"
touch /var/lib/mox/android-arm-ready
systemctl restart waydroid-container
"""),
    "cloud": ("Latest rclone for Google Drive and iCloud", """
curl -fsSL https://rclone.org/install.sh -o /tmp/rclone-install.sh
bash /tmp/rclone-install.sh || [ $? -eq 3 ]
"""),
    "home": ("Home automation (Home Assistant)", """
systemctl enable --now docker
mkdir -p /var/lib/mox/homeassistant
docker rm -f homeassistant 2>/dev/null || true
docker run -d --name homeassistant --restart=unless-stopped --network=host -e TZ="$(cat /etc/timezone 2>/dev/null || echo UTC)" -v /var/lib/mox/homeassistant:/config ghcr.io/home-assistant/home-assistant:stable
"""),
    "nvidia": ("NVIDIA driver, CUDA and video acceleration", """
ubuntu-drivers install
apt-get install -y nvidia-settings nvidia-vaapi-driver nvidia-opencl-dev nvidia-cuda-toolkit
"""),
    "torbrowser": ("Official Tor Browser", "apt-get install -y torbrowser-launcher"),
    "dialer": ("MOX Dialer (Asterisk call center)", "bash /usr/lib/mox/dialer/install.sh"),
    "apps": ("Spotify, Telegram and Discord (Flatpak)", """
flatpak remote-add --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo
flatpak install -y --system flathub com.spotify.Client org.telegram.desktop com.discordapp.Discord com.visualstudio.code
"""),
    "creator": ("Creator pack: GIMP, Inkscape, Kdenlive, OBS Studio, Blender, Audacity", "apt-get install -y gimp inkscape kdenlive obs-studio blender audacity"),
    "chat": ("SimpleX Chat private messenger", """
mkdir -p /opt/mox/simplex
if curl -fL https://github.com/simplex-chat/simplex-chat/releases/latest/download/simplex-desktop-x86_64.AppImage -o /opt/mox/simplex/SimpleX.AppImage; then
  chmod 755 /opt/mox/simplex/SimpleX.AppImage
else
  rm -f /opt/mox/simplex/SimpleX.AppImage
  flatpak install -y --system flathub chat.simplex.simplex
fi
"""),
    "quantum-mail": ("Post-quantum age 1.3 for MOX Quantum Mail", "bash /usr/lib/mox/install-age.sh"),
    "mailserver": ("Your own mail server (Stalwart) for your domain. Run it on a server with a public IP", """
apt-get install -y curl ca-certificates
curl --proto '=https' --tlsv1.2 -sSf https://get.stalw.art/install.sh -o /tmp/stalwart-install.sh
sh /tmp/stalwart-install.sh
rm -f /tmp/stalwart-install.sh
for port in 25 465 587 993 443 8080; do ufw allow "$port/tcp"; done
systemctl enable --now stalwart
sleep 3
echo
echo "Open http://THIS-SERVER:8080/admin and sign in as admin with the password below."
journalctl -u stalwart -n 200 --no-pager | grep -A8 'bootstrap mode' | tail -9 || true
echo "Then run: mox mail dns YOURDOMAIN SERVER_IP   and close port 8080 when setup is done: ufw delete allow 8080/tcp"
"""),
    "games": ("SuperTuxKart racing game", "apt-get install -y supertuxkart"),
    "windows": ("Windows apps (Wine)", "apt-get install -y wine winetricks"),
    "mac": ("Mac apps (Darling, compiles from source and takes about an hour)", """
apt-get install -y git cmake clang devscripts equivs
rm -rf /opt/mox/src/darling && mkdir -p /opt/mox/src
git clone --recursive --depth 1 https://github.com/darlinghq/darling.git /opt/mox/src/darling
cd /opt/mox/src/darling
mk-build-deps -i -r -t 'apt-get -y --no-install-recommends' debian/control
mkdir -p build && cd build
cmake .. -DCMAKE_BUILD_TYPE=Release
make -j"$(nproc)"
make install
"""),
    "iphone": ("Old iPhone apps (touchHLE, compiles from source)", """
apt-get install -y git cargo rustc cmake clang libboost-dev libsdl2-dev
rm -rf /opt/mox/src/touchHLE && mkdir -p /opt/mox/src
git clone --recursive --depth 1 https://github.com/touchHLE/touchHLE.git /opt/mox/src/touchHLE
cd /opt/mox/src/touchHLE
cargo build --release
install -m755 target/release/touchHLE /usr/local/bin/touchHLE
"""),
    "ollama": ("Local AI models (Ollama)", "curl -fsSL https://ollama.com/install.sh | sh"),
    "firefox": ("Firefox (Mozilla's own packages)", """
install -d -m755 /etc/apt/keyrings
curl -fsSL https://packages.mozilla.org/apt/repo-signing-key.gpg -o /etc/apt/keyrings/packages.mozilla.org.asc
echo 'deb [signed-by=/etc/apt/keyrings/packages.mozilla.org.asc] https://packages.mozilla.org/apt mozilla main' > /etc/apt/sources.list.d/mozilla.list
printf 'Package: firefox*\\nPin: origin packages.mozilla.org\\nPin-Priority: 1001\\n' > /etc/apt/preferences.d/mozilla
apt-get update && apt-get install -y firefox
"""),
    "metasploit": ("Metasploit Framework (Rapid7's installer)", """
curl -fsSL https://raw.githubusercontent.com/rapid7/metasploit-omnibus/master/config/templates/metasploit-framework-wrappers/msfupdate.erb -o /tmp/msfinstall
bash /tmp/msfinstall
"""),
    "zap": ("OWASP ZAP web scanner (Flatpak)", "flatpak install -y --system flathub org.zaproxy.ZAP"),
    "ghidra": ("Ghidra reverse engineering suite (Flatpak)", "flatpak install -y --system flathub org.ghidra_sre.Ghidra"),
    "ai-stack": ("PyTorch, Transformers and Jupyter in /opt/mox/ai", """
/opt/mox/ai/bin/pip install torch torchvision transformers accelerate datasets jupyterlab
"""),
}


# What proves each add-on is really there.
CHECKS = {
    "android": ["waydroid", "/var/lib/waydroid/images/system.img"], "android-arm": ["/var/lib/mox/android-arm-ready"],
    "cloud": ["rclone"], "home": ["/var/lib/mox/homeassistant/configuration.yaml"], "nvidia": ["nvidia-smi"],
    "torbrowser": ["torbrowser-launcher"], "dialer": ["/opt/mox-dialer/moxdialer/server.py"], "creator": ["gimp", "blender"],
    "windows": ["wine"], "mac": ["darling"], "iphone": ["touchHLE"], "ollama": ["ollama"], "metasploit": ["msfconsole"],
    "ai-stack": ["/opt/mox/ai/bin/jupyter"], "games": ["supertuxkart"], "mailserver": ["/usr/local/bin/stalwart"],
    "firefox": ["firefox"],
}
FLATPAKS = {"apps": "com.spotify.Client", "zap": "org.zaproxy.ZAP", "ghidra": "org.ghidra_sre.Ghidra"}
MARKS = Path("/var/lib/mox/addons")


def is_installed(name):
    """True when an add-on is really on this PC, however it got there."""
    if name == "quantum-mail":
        from . import mail
        return mail.pq_ready()
    if name == "chat":
        return Path("/opt/mox/simplex/SimpleX.AppImage").exists() or _has_flatpak("chat.simplex.simplex")
    if name in FLATPAKS:
        return _has_flatpak(FLATPAKS[name])
    if name in CHECKS:
        return all(Path(item).exists() if item.startswith("/") else shutil.which(item) for item in CHECKS[name])
    return (MARKS / name).exists()


def _has_flatpak(app):
    if not shutil.which("flatpak"):
        return False
    return subprocess.run(["flatpak", "info", app], capture_output=True, check=False).returncode == 0


def install(name):
    if name not in ADDONS:
        print(f"Unknown add-on: {name}. Run 'mox get' to see the list.")
        return 2
    label, script = ADDONS[name]
    print(f"Installing {label}...")
    if os.geteuid() != 0:
        return subprocess.run(["pkexec", "mox", "get", name], check=False).returncode
    code = subprocess.run(["bash", "-euxo", "pipefail", "-c", script], check=False).returncode
    if code == 0:
        MARKS.mkdir(parents=True, exist_ok=True)
        (MARKS / name).touch()
    return code
