#!/bin/bash
# Runs inside the new system during the ISO build.
set -euxo pipefail
BLUR_COMMIT=2930ef1373dc7e77fa2571c009f47f0514951b0a
export DEBIAN_FRONTEND=noninteractive LC_ALL=C.UTF-8 HOME=/root
if [[ -f /tmp/mox-ca.crt ]]; then
  export NODE_EXTRA_CA_CERTS=/tmp/mox-ca.crt PIP_CERT=/tmp/mox-ca.crt SSL_CERT_FILE=/tmp/mox-ca.crt GIT_SSL_CAINFO=/tmp/mox-ca.crt REQUESTS_CA_BUNDLE=/tmp/mox-ca.crt
  unset PIP_CONFIG_FILE
fi
printf '#!/bin/sh\nexit 101\n' > /usr/sbin/policy-rc.d
chmod +x /usr/sbin/policy-rc.d

cat > /etc/apt/sources.list.d/ubuntu.sources <<'SRC'
Types: deb
URIs: http://archive.ubuntu.com/ubuntu/
Suites: resolute resolute-updates resolute-security
Components: main restricted universe multiverse
Signed-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg
SRC
rm -f /etc/apt/sources.list
apt-get update

echo 'wireshark-common wireshark-common/install-setuid boolean true' | debconf-set-selections
echo 'keyboard-configuration keyboard-configuration/layoutcode string us' | debconf-set-selections
mapfile -t packages < /tmp/mox-packages.list
apt-get install -y --no-install-recommends "${packages[@]}"

sed -i 's/^# *en_US.UTF-8/en_US.UTF-8/' /etc/locale.gen
locale-gen
update-locale LANG=en_US.UTF-8

cat > /etc/netplan/01-network-manager.yaml <<'NET'
network:
  version: 2
  renderer: NetworkManager
NET
chmod 600 /etc/netplan/01-network-manager.yaml

cat > /etc/casper.conf <<'CASPER'
export USERNAME="mox"
export USERFULLNAME="MOX Live"
export HOST="mox"
export BUILD_SYSTEM="Ubuntu"
export FLAVOUR="MOX"
CASPER
echo mox > /etc/hostname

# Blur for the glass look
rm -rf /tmp/blur
git clone https://github.com/aunetx/blur-my-shell /tmp/blur
git -C /tmp/blur checkout "$BLUR_COMMIT"
apt-get install -y --no-install-recommends libglib2.0-dev-bin gettext gnome-shell-common
make -C /tmp/blur build
target=/usr/share/gnome-shell/extensions/blur-my-shell@aunetx
mkdir -p "$target"
unzip -q -o /tmp/blur/build/blur-my-shell@aunetx.shell-extension.zip -d "$target"
cp "$target"/schemas/*.gschema.xml /usr/share/glib-2.0/schemas/

# AI tools
python3 -m venv /opt/mox/ai
/opt/mox/ai/bin/pip install --upgrade pip anthropic openai
npm install -g @anthropic-ai/claude-code @openai/codex

# Add-ons that can be baked in when their sources are reachable
if curl -fsS -m 30 https://repo.waydro.id -o /tmp/waydroid-repo.sh; then
  bash /tmp/waydroid-repo.sh || bash /tmp/waydroid-repo.sh -s noble || true
  apt-get install -y --no-install-recommends waydroid || echo "Waydroid stays an add-on in this build"
fi

# Firewall on by default: nothing comes in unless the user allows it
sed -i 's/^ENABLED=.*/ENABLED=yes/' /etc/ufw/ufw.conf
sed -i 's/^DEFAULT_INPUT_POLICY=.*/DEFAULT_INPUT_POLICY="DROP"/; s/^DEFAULT_FORWARD_POLICY=.*/DEFAULT_FORWARD_POLICY="ACCEPT"/' /etc/default/ufw
sed -i 's/^LOGLEVEL=.*/LOGLEVEL=low/' /etc/ufw/ufw.conf
grep -q '^LOGLEVEL=' /etc/ufw/ufw.conf || echo 'LOGLEVEL=low' >> /etc/ufw/ufw.conf
systemctl enable ufw clamav-freshclam

# SimpleX Chat, when its release file is reachable
mkdir -p /opt/mox/simplex
if curl -fL -m 300 https://github.com/simplex-chat/simplex-chat/releases/latest/download/simplex-desktop-x86_64.AppImage -o /opt/mox/simplex/SimpleX.AppImage; then
  chmod 755 /opt/mox/simplex/SimpleX.AppImage
else
  rm -f /opt/mox/simplex/SimpleX.AppImage
  echo "SimpleX Chat stays an add-on in this build"
fi

# MOX keeps one dock, so the Windows-style taskbar can't be turned on by accident
rm -rf /usr/share/gnome-shell/extensions/window-list@gnome-shell-extensions.gcampax.github.com

# Post-quantum age for MOX Quantum Mail
bash /usr/lib/mox/install-age.sh || echo "Quantum Mail's age 1.3 will be installed on first boot"

# Ad block on from the start
python3 - <<'PY' || echo "Ad block list will be fetched on first boot"
import sys
sys.path.insert(0, "/usr/lib/mox")
from moxos import adblock
print(adblock.update(), "domains blocked")
PY

# Latest rclone for iCloud, when reachable
curl -fsSL -m 60 https://rclone.org/install.sh -o /tmp/rclone-install.sh && { bash /tmp/rclone-install.sh || true; }
rm -f /tmp/rclone-install.sh

# Identity
dpkg-divert --local --rename --add /usr/lib/os-release
dpkg-divert --local --rename --add /etc/lsb-release
cat > /usr/lib/os-release <<OS
PRETTY_NAME="MOX $(cat /usr/lib/mox/VERSION)"
NAME="MOX"
VERSION_ID="$(cut -d. -f1,2 /usr/lib/mox/VERSION)"
VERSION="$(cat /usr/lib/mox/VERSION)"
VERSION_CODENAME=resolute
ID=mox
ID_LIKE="ubuntu debian"
UBUNTU_CODENAME=resolute
HOME_URL="https://github.com/balajsajjad7-bot/mox"
OS
ln -sf ../usr/lib/os-release /etc/os-release
printf 'DISTRIB_ID=MOX\nDISTRIB_RELEASE=%s\nDISTRIB_CODENAME=resolute\nDISTRIB_DESCRIPTION="MOX"\n' "$(cat /usr/lib/mox/VERSION)" > /etc/lsb-release
printf 'MOX %s\n' "$(cat /usr/lib/mox/VERSION)" > /etc/issue
printf 'GRUB_DISTRIBUTOR="MOX"\nGRUB_TIMEOUT_STYLE=hidden\nGRUB_TIMEOUT=2\nGRUB_CMDLINE_LINUX_DEFAULT="quiet splash"\n' > /etc/default/grub.d/90-mox.cfg

# Boot animation
update-alternatives --install /usr/share/plymouth/themes/default.plymouth default.plymouth /usr/share/plymouth/themes/mox/mox.plymouth 200
update-alternatives --set default.plymouth /usr/share/plymouth/themes/mox/mox.plymouth

# Desktop databases
dconf update
glib-compile-schemas /usr/share/glib-2.0/schemas
update-mime-database /usr/share/mime
update-desktop-database /usr/share/applications
gtk-update-icon-cache -f /usr/share/icons/hicolor || true

systemctl enable NetworkManager gdm3 mox-auto-update.timer mox-software-graphics.service mox-live-display.service mox-adblock-update.timer mox-firstboot.timer mox-optimize
systemctl disable tor bettercap containerd docker.service lxc-net libvirt-guests || true
systemctl enable docker.socket || true
systemctl --global enable mox-widgets.service mox-shield-scan.timer
sed -i 's/^#user_allow_other/user_allow_other/' /etc/fuse.conf || true
systemctl mask casper-md5check.service || true
apt-get purge -y gnome-initial-setup || true
for group in docker wireshark libvirt kvm; do getent group "$group" >/dev/null || groupadd "$group"; done

update-initramfs -c -k all || update-initramfs -u -k all

chmod 0440 /etc/sudoers.d/mox-health
visudo -cf /etc/sudoers.d/mox-health

cat > /etc/apt/apt.conf.d/20auto-upgrades <<'APT'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
APT::Periodic::AutocleanInterval "7";
APT
sed -i 's|^//\s*"${distro_id}:${distro_codename}-updates";|        "${distro_id}:${distro_codename}-updates";|' /etc/apt/apt.conf.d/50unattended-upgrades || true

# Clean up
rm -f /usr/sbin/policy-rc.d /tmp/mox-* /tmp/waydroid-repo.sh
rm -rf /tmp/blur /root/.npm /root/.cache
apt-get clean
rm -rf /var/lib/apt/lists/* /var/log/*.log
truncate -s 0 /etc/machine-id
rm -f /var/lib/dbus/machine-id /etc/ssh/ssh_host_*
