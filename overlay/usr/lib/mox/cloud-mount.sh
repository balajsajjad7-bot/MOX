#!/bin/bash
# Mounts a connected cloud drive into ~/Drives.
label() { case "$1" in google) echo "Google Drive";; icloud) echo "iCloud Drive";; *) echo "$1";; esac; }
if [[ "$1" == "--label" ]]; then label "$2"; exit 0; fi
target="$HOME/Drives/$(label "$1")"
mkdir -p "$target"
exec rclone mount "$1:" "$target" --vfs-cache-mode full --dir-cache-time 1h --vfs-cache-max-size 20G
