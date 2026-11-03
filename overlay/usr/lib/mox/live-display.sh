#!/bin/bash
# Live session only: keep the auto-login desktop in front while the system settles.
# On slow machines the login screen can start late and take over the display.
for _ in $(seq 1 180); do
  session="$(loginctl list-sessions --no-legend --no-pager | awk '$3=="mox" && $4=="seat0" {print $1; exit}')"
  if [[ -n "$session" ]]; then
    vt="$(loginctl show-session "$session" -p VTNr --value)"
    if [[ -n "$vt" && "$vt" != 0 ]] && pgrep -u mox -f 'gnome-shell --mode=' >/dev/null; then
      [[ "$(cat /sys/class/tty/tty0/active)" == "tty$vt" ]] || chvt "$vt"
    fi
  fi
  sleep 5
done
