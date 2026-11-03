#!/bin/bash
# Shows MOX names in menus and on the login screen. Safe to run again after package updates.
# The upstream programs keep their own credits and licences.
set -u
apps=/usr/share/applications; local=/usr/local/share/applications
mkdir -p "$local"
# Changes only the app's own name, not the names of its right-click actions.
entry_name() {
  awk -v name="$1" '
    /^\[/ { top = ($0 == "[Desktop Entry]") }
    top && /^Name\[/ { next }
    top && /^Name=/ { print "Name=" name; next }
    { print }' "$2"
}
rename() {
  [[ -f "$apps/$1.desktop" ]] && entry_name "$2" "$apps/$1.desktop" > "$local/$1.desktop"
  return 0
}
hide() {
  [[ -f "$apps/$1.desktop" ]] && sed '/^\[Desktop Entry\]/a NoDisplay=true' "$apps/$1.desktop" > "$local/$1.desktop"
  return 0
}
rename org.gnome.Nautilus "MOX Files"
rename org.gnome.Settings "MOX Settings"
rename org.gnome.TextEditor "MOX Notes"
rename org.gnome.Calculator "MOX Calculator"
rename org.gnome.Loupe "MOX Photos"
rename org.gnome.Calendar "MOX Calendar"
rename org.gnome.clocks "MOX Clock"
rename org.gnome.Weather "MOX Weather"
rename org.gnome.Characters "MOX Characters"
rename org.gnome.Logs "MOX Logs"
rename org.gnome.font-viewer "MOX Fonts"
rename org.gnome.DiskUtility "MOX Disks"
rename org.gnome.baobab "MOX Disk Usage"
rename org.gnome.SystemMonitor "MOX System Monitor"
rename org.gnome.Geary "MOX Mailbox"
hide org.gnome.Ptyxis
hide org.gnome.Extensions
hide org.gnome.Shell.Extensions
update-desktop-database "$local" 2>/dev/null || true
for file in /usr/share/wayland-sessions/*.desktop /usr/share/xsessions/*.desktop; do
  [[ -f "$file" ]] || continue
  entry_name MOX "$file" > "$file.mox" && cat "$file.mox" > "$file"
  rm -f "$file.mox"
done
version="$(cat /usr/lib/mox/VERSION)"
if [[ -f /usr/lib/os-release ]]; then
  sed -i "s/^PRETTY_NAME=.*/PRETTY_NAME=\"MOX $version (Linux based)\"/" /usr/lib/os-release
fi
true
