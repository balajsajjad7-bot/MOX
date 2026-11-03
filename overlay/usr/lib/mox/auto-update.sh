#!/bin/bash
# Keeps MOX and its apps current. Create /etc/mox/auto-update-off to stop it.
set -u
exec >>/var/log/mox-update.log 2>&1
echo "MOX auto update: $(date -Is)"
mox update
flatpak update -y --noninteractive || true
mox update --check > /var/lib/mox/update-status 2>&1 || true
