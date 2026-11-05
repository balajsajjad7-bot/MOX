#!/bin/bash
# First boot with internet: bring MOX fully up to date and install everything too
# large for the ISO. Each finished step is remembered, so a retry skips it.
set -u
log=/var/log/mox-firstboot.log
state=/var/lib/mox/firstboot
mkdir -p "$state"
exec >>"$log" 2>&1
echo "MOX first boot: $(date -Is)"
for _ in $(seq 1 30); do
  curl -fsS -m 5 -o /dev/null http://archive.ubuntu.com/ubuntu/ && online=1 && break
  sleep 2
done
[[ "${online:-0}" == 1 ]] || { echo "offline, will retry"; exit 1; }

step() {
  name="$1"; shift
  [[ -e "$state/$name" ]] && return 0
  echo "--- $name"
  echo "$name" > /run/mox-setup; chmod 644 /run/mox-setup
  if "$@"; then touch "$state/$name"; else echo "$name failed"; failed=1; fi
}
failed=0
export DEBIAN_FRONTEND=noninteractive
mox optimize >/dev/null 2>&1 || true
step update apt-get update
step upgrade apt-get -y -o Dpkg::Options::=--force-confold full-upgrade
step drivers ubuntu-drivers install
lspci | grep -qi nvidia && step nvidia mox get nvidia
step firmware sh -c 'fwupdmgr refresh --force; fwupdmgr update -y --no-reboot-check || true'
step flathub flatpak remote-add --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo
step signatures sh -c 'systemctl stop clamav-freshclam; freshclam; systemctl start clamav-freshclam'
step adblock mox adblock on
step cloud mox get cloud
[[ -f /etc/mox/office ]] || step chat mox get chat
step quantum-mail mox get quantum-mail
step apps mox get apps
step torbrowser mox get torbrowser
[[ -f /etc/mox/office ]] || step games mox get games
# Big tools only on PCs with room for them. Smaller PCs fetch them when first opened.
memory_gb=$(( $(awk '/MemTotal/{print $2}' /proc/meminfo) / 1000000 ))
free_gb=$(( $(df --output=avail / | tail -1) / 1000000 ))
if [[ ! -f /etc/mox/office ]] && (( memory_gb >= 8 && free_gb >= 60 )); then
  step android mox get android
  step ollama mox get ollama
  step creator mox get creator
fi
rm -f /run/mox-setup
[[ "$failed" == 0 ]] && touch /var/lib/mox/firstboot-done
exit "$failed"
