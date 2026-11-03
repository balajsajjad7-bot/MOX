#!/bin/bash
# MOX Sync: fetches the newest MOX from GitHub and installs it, with rollback.
# Used on the owner's own PCs. Other PCs get signed releases through `mox update`.
set -euo pipefail
ROOT="${MOX_SYNC_ROOT:-}"
REPO="${MOX_SYNC_REPO:-https://github.com/balajsajjad7-bot/MOX}"
state="$ROOT/var/lib/mox/sync"; src="$state/source"
mkdir -p "$state"
exec 9>"$state/lock"
flock -n 9 || { echo "MOX Sync is already running."; exit 0; }
if [[ -d "$src/.git" ]]; then
  git -C "$src" fetch -q --depth 1 origin main
  git -C "$src" reset -q --hard FETCH_HEAD
else
  rm -rf "$src"
  git clone -q --depth 1 --branch main "$REPO" "$src"
fi
new="$(git -C "$src" rev-parse HEAD)"
if [[ "$new" == "$(cat "$state/applied" 2>/dev/null || true)" && -z "${MOX_SYNC_FORCE:-}" ]]; then
  echo "MOX is up to date."
  exit 0
fi
check() { PYTHONPATH="$1" python3 -c "import moxos.cli as c, moxos.addons, moxos.update; c.build_parser()"; }
check "$src/overlay/usr/lib/mox" || { echo "The new version failed its check, so it wasn't installed."; exit 1; }

tar czf "$state/backup.tgz" -C "$ROOT/" usr/lib/mox
restore() { rm -rf "$ROOT/usr/lib/mox"; tar xzf "$state/backup.tgz" -C "$ROOT/"; echo "Update failed. The previous version was restored."; }
trap restore ERR
mkdir -p "$ROOT/usr" "$ROOT/etc/xdg" "$ROOT/etc/apt/apt.conf.d" "$ROOT/etc/dconf/db/local.d"
cp -a "$src/overlay/usr/." "$ROOT/usr/"
cp -a "$src/overlay/etc/xdg/." "$ROOT/etc/xdg/"
cp -a "$src/overlay/etc/apt/apt.conf.d/." "$ROOT/etc/apt/apt.conf.d/"
cp -a "$src/overlay/etc/dconf/db/local.d/00-mox" "$ROOT/etc/dconf/db/local.d/"
rm -rf "$ROOT/usr/lib/mox/dialer"
cp -a "$src/dialer" "$ROOT/usr/lib/mox/dialer"
if [[ -z "$ROOT" ]]; then
  export DEBIAN_FRONTEND=noninteractive
  mapfile -t wanted < <(grep -v '^#' /usr/lib/mox/sync-packages.list)
  apt-get install -y --no-install-recommends "${wanted[@]}" || echo "Some extra tools weren't installed. MOX will try again next time."
  bash /usr/lib/mox/rebrand.sh
  systemctl daemon-reload
  systemctl enable mox-firstboot.timer mox-optimize.service mox-sync.timer || true
  dconf update
  glib-compile-schemas /usr/share/glib-2.0/schemas
  update-desktop-database /usr/share/applications
  gtk-update-icon-cache -f /usr/share/icons/hicolor || true
  if [[ -d /opt/mox-dialer ]]; then cp -a /usr/lib/mox/dialer/moxdialer /usr/lib/mox/dialer/web /opt/mox-dialer/; systemctl restart mox-dialer || true; fi
fi
check "$ROOT/usr/lib/mox"
trap - ERR
echo "$new" > "$state/applied"
echo "MOX updated to ${new:0:7}. Log out and back in to see desktop changes."
