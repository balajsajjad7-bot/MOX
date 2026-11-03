#!/usr/bin/env bash
# Installs MOX Dialer on MOX or any Ubuntu server. Run as root.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
apt-get update
apt-get install -y asterisk python3-aiohttp openssl
install -d -m 750 -o asterisk -g asterisk /var/lib/mox-dialer
install -d -m 755 /opt/mox-dialer
cp -a "$here/moxdialer" "$here/web" /opt/mox-dialer/
cp "$here/asterisk/http.conf" "$here/asterisk/pjsip.conf" "$here/asterisk/extensions.conf" /etc/asterisk/
password="$(openssl rand -hex 24)"
sed "s/@ARI_PASSWORD@/$password/" "$here/asterisk/ari.conf.tmpl" > /etc/asterisk/ari.conf
touch /etc/asterisk/pjsip_mox.conf
grep -q "noload = chan_sip.so" /etc/asterisk/modules.conf || sed -i "/^\[modules\]/a noload = chan_sip.so" /etc/asterisk/modules.conf
chown asterisk:asterisk /etc/asterisk/ari.conf /etc/asterisk/pjsip_mox.conf
chmod 640 /etc/asterisk/ari.conf /etc/asterisk/pjsip_mox.conf
printf 'MOX_ARI_PASSWORD=%s\n' "$password" > /etc/mox-dialer.env
chmod 600 /etc/mox-dialer.env
if [[ ! -f /var/lib/mox-dialer/cert.pem ]]; then
  openssl req -x509 -newkey rsa:2048 -nodes -days 825 -subj "/CN=$(hostname)" \
    -keyout /var/lib/mox-dialer/key.pem -out /var/lib/mox-dialer/cert.pem
  chown asterisk:asterisk /var/lib/mox-dialer/key.pem /var/lib/mox-dialer/cert.pem
  chmod 600 /var/lib/mox-dialer/key.pem
fi
cat > /etc/systemd/system/mox-dialer.service <<'UNIT'
[Unit]
Description=MOX Dialer
After=network-online.target asterisk.service
Wants=asterisk.service

[Service]
User=asterisk
Group=asterisk
EnvironmentFile=/etc/mox-dialer.env
WorkingDirectory=/opt/mox-dialer
ExecStart=/usr/bin/python3 -m moxdialer.server --cert /var/lib/mox-dialer/cert.pem --key /var/lib/mox-dialer/key.pem
Restart=always
RestartSec=3
NoNewPrivileges=yes
ProtectSystem=full
ProtectHome=yes

[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable asterisk mox-dialer
systemctl restart asterisk
if command -v ufw >/dev/null; then
  ufw allow 8443/tcp
  ufw allow 5060/udp
  ufw allow 10000:20000/udp
fi
if [[ ! -s /var/lib/mox-dialer/dialer.db ]]; then
  cd /opt/mox-dialer
  sudo -u asterisk env MOX_DIALER_DB=/var/lib/mox-dialer/dialer.db python3 -m moxdialer.server --create-admin admin
fi
systemctl restart mox-dialer
echo "MOX Dialer is at https://$(hostname -I | awk '{print $1}'):8443"
