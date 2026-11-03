"""MOXWALL VPN: WireGuard tunnels, including one on a server you own."""
import ipaddress
import re
import subprocess
from pathlib import Path

from .common import run


class VPNError(Exception):
    pass


def tunnels():
    text = run(["nmcli", "-t", "-f", "NAME,TYPE,DEVICE", "connection", "show"])
    found = []
    for line in text.splitlines():
        parts = line.rsplit(":", 2)
        if len(parts) == 3 and parts[1] == "wireguard":
            found.append({"name": parts[0], "active": bool(parts[2])})
    return found


def import_config(path):
    if not Path(path).is_file():
        raise VPNError(f"{path} was not found.")
    return subprocess.run(["nmcli", "connection", "import", "type", "wireguard", "file", str(path)], check=False).returncode


def switch(name, up):
    return subprocess.run(["nmcli", "connection", "up" if up else "down", name], check=False).returncode


def _keypair():
    private = subprocess.run(["wg", "genkey"], capture_output=True, text=True, check=True).stdout.strip()
    public = subprocess.run(["wg", "pubkey"], input=private, capture_output=True, text=True, check=True).stdout.strip()
    return private, public


def server_files(host, port=51820, keys=None):
    """Return a server setup script and a client config for one VPN user."""
    if not re.fullmatch(r"[A-Za-z0-9.:-]+", host):
        raise VPNError("Enter the server's IP address or host name.")
    if ":" in host:
        ipaddress.IPv6Address(host)
        endpoint = f"[{host}]:{port}"
    else:
        endpoint = f"{host}:{port}"
    server_private, server_public, client_private, client_public = (keys or (_keypair() + _keypair()))[:4]
    # A preshared key adds a symmetric layer that a future quantum computer can't break through the key exchange.
    shared = subprocess.run(["wg", "genpsk"], capture_output=True, text=True, check=True).stdout.strip() if keys is None else keys[4]
    script = f"""#!/bin/bash
# Run as root on your own Ubuntu or Debian server.
set -euo pipefail
apt-get update
apt-get install -y wireguard iptables
device="$(ip route show default | awk '{{print $5; exit}}')"
umask 077
cat > /etc/wireguard/moxwall0.conf <<CONF
[Interface]
Address = 10.66.0.1/24
ListenPort = {port}
PrivateKey = {server_private}
PostUp = iptables -t nat -A POSTROUTING -o $device -j MASQUERADE; iptables -A FORWARD -i moxwall0 -j ACCEPT; iptables -A FORWARD -o moxwall0 -j ACCEPT
PostDown = iptables -t nat -D POSTROUTING -o $device -j MASQUERADE; iptables -D FORWARD -i moxwall0 -j ACCEPT; iptables -D FORWARD -o moxwall0 -j ACCEPT

[Peer]
PublicKey = {client_public}
PresharedKey = {shared}
AllowedIPs = 10.66.0.2/32
CONF
echo 'net.ipv4.ip_forward=1' > /etc/sysctl.d/99-moxwall.conf
sysctl --system >/dev/null
systemctl enable --now wg-quick@moxwall0
echo 'MOXWALL VPN server is running. Open UDP port {port} in your cloud firewall.'
"""
    client = f"""[Interface]
PrivateKey = {client_private}
Address = 10.66.0.2/32
DNS = 1.1.1.1

[Peer]
PublicKey = {server_public}
PresharedKey = {shared}
Endpoint = {endpoint}
AllowedIPs = 0.0.0.0/0, ::/0
PersistentKeepalive = 25
"""
    return script, client


def make_server(host, folder):
    script, client = server_files(host)
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    (folder / "server-setup.sh").write_text(script)
    (folder / "moxwall.conf").write_text(client)
    (folder / "server-setup.sh").chmod(0o600)
    (folder / "moxwall.conf").chmod(0o600)
    return folder
