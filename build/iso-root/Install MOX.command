#!/bin/bash
# MOX Installer for Intel Macs. Double-click on the mounted ISO.
here="$(cd "$(dirname "$0")" && pwd)"
LIVE_GB=6
say_stop() { echo; echo "$1"; read -r -p "Press Return to close."; exit 1; }
[ "$(sysctl -n hw.optional.arm64 2>/dev/null)" = 1 ] && say_stop "This Mac uses Apple silicon. MOX is built for Intel and AMD processors, so it can't install on this Mac."
[ "$(uname -m)" = x86_64 ] || say_stop "MOX needs an Intel Mac."
if system_profiler SPiBridgeDataType 2>/dev/null | grep -q "T2"; then
  echo "This Mac has a T2 security chip. Before going on, start in Recovery and open"
  echo "Startup Security Utility, then set 'No Security'. The keyboard, trackpad, WiFi"
  echo "and sound may not work in MOX on T2 Macs."
fi
container="$(diskutil info / | awk -F': *' '/APFS Physical Store/{print $2}')"
[ -n "$container" ] || say_stop "Couldn't find the APFS disk. Install MOX from a USB drive."
read -r -p "How many GB should MOX get? (40 or more) [80]: " gb
gb="${gb:-80}"
[ "$gb" -ge 40 ] 2>/dev/null || say_stop "MOX needs at least 40 GB."
total="$(diskutil info "$container" | awk -F'[()]' '/Disk Size/{split($2,a," "); print a[1]}')"
keep=$(( total - (gb + LIVE_GB) * 1000000000 ))
echo
echo "This will shrink macOS by $((gb + LIVE_GB)) GB, copy the MOX installer, and restart once."
echo "Back up with Time Machine first. Your files stay in place."
read -r -p "Type YES to continue: " yes
[ "$yes" = YES ] || say_stop "Nothing was changed."
sudo diskutil apfs resizeContainer "$container" "$keep" MS-DOS MOXLIVE "${LIVE_GB}g" "Free Space" %noformat% 0 || say_stop "Couldn't resize the disk."
echo "Copying MOX. This takes a few minutes..."
sudo rsync -a --exclude autorun.inf "$here/" /Volumes/MOXLIVE/ || say_stop "Copying failed."
sudo bless --mount /Volumes/MOXLIVE --setBoot --nextonly --file /Volumes/MOXLIVE/EFI/BOOT/BOOTX64.EFI || say_stop "Couldn't set the startup disk."
read -r -p "Ready. Press Return to restart into the MOX installer."
sudo shutdown -r now
