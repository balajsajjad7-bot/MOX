#!/bin/bash
# MOX Office mode: hardens a PC for office use. Usage: office.sh on|off|check
set -u
ROOT="${MOX_OFFICE_ROOT:-}"
flag="$ROOT/etc/mox/office"
test_key=c4703bcf36e4beab56d738c8e797b41ea0526cb5cc8f687dd36413ae21a84ab8
journal="$ROOT/etc/systemd/journald.conf.d/95-mox-office.conf"
audit="$ROOT/etc/audit/rules.d/mox-office.rules"
dconf_file="$ROOT/etc/dconf/db/local.d/60-mox-office"
locks="$ROOT/etc/dconf/db/local.d/locks/mox-office"
password="$ROOT/etc/security/pwquality.conf.d/mox-office.conf"
sysctl_file="$ROOT/etc/sysctl.d/90-mox-office.conf"
upgrades="$ROOT/etc/apt/apt.conf.d/21-mox-office"
sbom="$ROOT/var/lib/mox/sbom.tsv"
service() { [[ -z "$ROOT" ]] && systemctl "$@" 2>/dev/null; return 0; }

need_root() { [[ "$(id -u)" == 0 ]] || { echo "Run with sudo."; exit 1; }; }

turn_on() {
  need_root
  mkdir -p "$(dirname "$flag")" "$(dirname "$journal")" "$(dirname "$dconf_file")" "$(dirname "$locks")" "$(dirname "$password")" "$(dirname "$sysctl_file")" "$(dirname "$sbom")" "$ROOT/var/log/journal"
  touch "$flag"
  echo "Installing audit and password tools..."
  export DEBIAN_FRONTEND=noninteractive
  apt-get install -y --no-install-recommends auditd libpam-pwquality unattended-upgrades || echo "Some packages weren't installed. Check your internet and run this again."

  echo "Keeping system logs on disk..."
  printf '[Journal]\nStorage=persistent\nSystemMaxUse=1G\nMaxRetentionSec=180day\n' > "$journal"
  service restart systemd-journald

  echo "Turning on audit rules..."
  mkdir -p "$(dirname "$audit")"
  cat > "$audit" <<'RULES'
-w /etc/passwd -p wa -k accounts
-w /etc/group -p wa -k accounts
-w /etc/shadow -p wa -k accounts
-w /etc/sudoers -p wa -k admin
-w /etc/sudoers.d/ -p wa -k admin
-w /etc/ssh/ -p wa -k remote
-w /etc/systemd/system/ -p wa -k services
-w /usr/lib/mox/ -p wa -k mox
-w /var/log/lastlog -p wa -k logins
-w /var/log/faillog -p wa -k logins
RULES
  service enable --now auditd
  [[ -z "$ROOT" ]] && augenrules --load >/dev/null 2>&1

  echo "Removing attack tools..."
  mapfile -t tools < <(grep -v '^#' "$ROOT/usr/lib/mox/attack-tools.list" 2>/dev/null || grep -v '^#' /usr/lib/mox/attack-tools.list)
  present=()
  for tool in "${tools[@]}"; do dpkg -s "$tool" >/dev/null 2>&1 && present+=("$tool"); done
  ((${#present[@]})) && apt-get purge -y "${present[@]}"
  apt-get autoremove -y --purge >/dev/null 2>&1

  echo "Turning off GitHub Sync. This PC will only accept signed updates..."
  rm -f "$ROOT/etc/mox/sync-on"
  service disable --now mox-sync.timer

  echo "Setting screen lock, passwords and system protections..."
  cat > "$dconf_file" <<'SETTINGS'
[org/gnome/desktop/session]
idle-delay=uint32 300

[org/gnome/desktop/screensaver]
lock-enabled=true
lock-delay=uint32 0

[org/gnome/desktop/notifications]
show-in-lock-screen=false
SETTINGS
  printf '/org/gnome/desktop/session/idle-delay\n/org/gnome/desktop/screensaver/lock-enabled\n/org/gnome/desktop/screensaver/lock-delay\n' > "$locks"
  command -v dconf >/dev/null && dconf update
  printf 'minlen = 12\nminclass = 3\ndictcheck = 1\nusercheck = 1\nretry = 3\n' > "$password"
  cat > "$sysctl_file" <<'KERNEL'
kernel.kptr_restrict = 2
kernel.dmesg_restrict = 1
kernel.yama.ptrace_scope = 1
kernel.unprivileged_bpf_disabled = 1
net.core.bpf_jit_harden = 2
net.ipv4.conf.all.rp_filter = 1
net.ipv4.conf.default.rp_filter = 1
net.ipv4.conf.all.accept_redirects = 0
net.ipv4.conf.default.accept_redirects = 0
net.ipv4.conf.all.send_redirects = 0
net.ipv4.conf.all.accept_source_route = 0
net.ipv4.tcp_syncookies = 1
net.ipv6.conf.all.accept_redirects = 0
KERNEL
  [[ -z "$ROOT" ]] && sysctl --system >/dev/null 2>&1
  printf 'APT::Periodic::Update-Package-Lists "1";\nAPT::Periodic::Unattended-Upgrade "1";\n' > "$upgrades"

  echo "Locking the firewall..."
  if [[ -z "$ROOT" ]] && command -v ufw >/dev/null; then
    ufw default deny incoming >/dev/null; ufw default allow outgoing >/dev/null; ufw --force enable >/dev/null
    if [[ -d /opt/mox-dialer ]]; then
      ufw delete allow 8443/tcp >/dev/null 2>&1
      ufw delete allow 5060/udp >/dev/null 2>&1
      for net in 10.0.0.0/8 172.16.0.0/12 192.168.0.0/16; do
        ufw allow from "$net" to any port 8443 proto tcp >/dev/null
        ufw allow from "$net" to any port 5060 proto udp >/dev/null
      done
    fi
  fi

  echo "Writing the software list..."
  dpkg-query -W -f='${Package}\t${Version}\t${Architecture}\n' > "$sbom"
  chmod 644 "$sbom"
  echo
  check
}

turn_off() {
  need_root
  rm -f "$flag" "$journal" "$audit" "$dconf_file" "$locks" "$password" "$sysctl_file" "$upgrades"
  command -v dconf >/dev/null && dconf update
  service restart systemd-journald
  [[ -z "$ROOT" ]] && sysctl --system >/dev/null 2>&1
  echo "Office mode is off. Attack tools stay removed until you run: sudo mox get pentest"
}

pass=0; fail=0
line() {
  if [[ "$1" == 0 ]]; then printf '  PASS  %s\n' "$2"; pass=$((pass + 1))
  else printf '  FIX   %s\n        %s\n' "$2" "$3"; fail=$((fail + 1)); fi
}

check() {
  echo "MOX Office check"
  [[ -f "$flag" ]]; line $? "Office mode is on" "Run: sudo mox office on"
  if [[ -f "$ROOT/usr/share/mox/keys/creator.pub" ]] && [[ "$(sha256sum < "$ROOT/usr/share/mox/keys/creator.pub" | cut -c1-64)" != "$test_key" ]]; then line 0 "Using your own update signing key" ""; else line 1 "Using your own update signing key" "Run tools/mox-setup-owner on your PC"; fi
  lsblk -no TYPE,MOUNTPOINTS 2>/dev/null | grep -q crypt || [[ "$(lsblk -no TYPE "$(findmnt -no SOURCE / 2>/dev/null)" 2>/dev/null | head -1)" == crypt ]]; line $? "Disk is encrypted" "Reinstall with Encrypt system turned on. API keys and mail keys depend on this"
  mokutil --sb-state 2>/dev/null | grep -q enabled; line $? "Secure Boot is on" "Run: sudo mox secureboot"
  [[ -f "$journal" ]]; line $? "Logs are kept on disk" "Run: sudo mox office on"
  command -v auditd >/dev/null && [[ -f "$audit" ]]; line $? "Audit rules are installed" "Run: sudo mox office on"
  found=0; while read -r tool; do [[ "$tool" == \#* || -z "$tool" ]] && continue; dpkg -s "$tool" >/dev/null 2>&1 && found=1; done < "$ROOT/usr/lib/mox/attack-tools.list"
  [[ "$found" == 0 ]]; line $? "Attack tools are removed" "Run: sudo mox office on"
  [[ ! -f "$ROOT/etc/mox/sync-on" ]]; line $? "GitHub Sync is off" "Run: sudo mox sync off"
  [[ -f "$dconf_file" ]]; line $? "Screen locks after 5 minutes" "Run: sudo mox office on"
  [[ -f "$password" ]]; line $? "Strong passwords are required" "Run: sudo mox office on"
  ufw status 2>/dev/null | grep -q 'Status: active' || systemctl is-enabled ufw >/dev/null 2>&1; line $? "Firewall is on" "Run: sudo ufw enable"
  [[ -s "$sbom" ]]; line $? "Software list is saved" "Run: sudo mox office on"
  echo
  echo "$pass passed, $fail to fix."
  [[ "$fail" == 0 ]]
}

case "${1:-check}" in
  on) turn_on ;;
  off) turn_off ;;
  check) check ;;
  *) echo "Usage: mox office [on|off|check]"; exit 2 ;;
esac
