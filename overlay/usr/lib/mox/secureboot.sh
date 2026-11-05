#!/bin/bash
# MOX Secure Boot doctor.
#   check          show what the firmware trusts and whether each boot file is signed
#   fix            reinstall the signed boot chain (keeps a backup of the old one)
#   mok FILE.efi   sign your own EFI file with a Machine Owner Key
set -u
esp="${MOX_ESP:-/boot/efi}"
kernel="${MOX_KERNEL:-/boot/vmlinuz}"
action="${1:-check}"
bad=0

signers() { sbverify --list "$1" 2>/dev/null | grep -E '^ *- subject:' | sed 's/.*CN=//'; }

show_file() {
  local label="$1" file="$2" need="$3" who
  if [[ ! -f "$file" ]]; then
    printf '  MISSING   %s (%s)\n' "$label" "$file"; bad=1; return
  fi
  who="$(signers "$file")"
  if grep -qi "$need" <<<"$who"; then
    printf '  SIGNED    %s\n' "$label"
  elif [[ -n "$who" ]]; then
    printf '  WRONG     %s is signed by: %s\n' "$label" "$(head -1 <<<"$who")"; bad=1
  else
    printf '  UNSIGNED  %s\n' "$label"; bad=1
  fi
}

check() {
  command -v sbverify >/dev/null || { echo "Install the checker first: sudo apt-get install -y sbsigntool mokutil"; return 1; }
  echo "Firmware"
  if [[ -d /sys/firmware/efi ]]; then
    echo "  Mode: UEFI"
    echo "  $(mokutil --sb-state 2>&1 | head -1)"
    local db; db="$(mokutil --db 2>/dev/null)"
    grep -q "Microsoft Corporation UEFI CA 2011" <<<"$db" && echo "  Trusts Microsoft UEFI CA 2011: yes" || echo "  Trusts Microsoft UEFI CA 2011: no"
    grep -q "Microsoft UEFI CA 2023" <<<"$db" && echo "  Trusts Microsoft UEFI CA 2023: yes" || echo "  Trusts Microsoft UEFI CA 2023: no"
  else
    echo "  Mode: not UEFI, or firmware details aren't available here"
  fi
  echo "Boot files in $esp"
  show_file "EFI/ubuntu/shimx64.efi" "$esp/EFI/ubuntu/shimx64.efi" "Microsoft"
  show_file "EFI/ubuntu/grubx64.efi" "$esp/EFI/ubuntu/grubx64.efi" "Canonical"
  show_file "EFI/BOOT/BOOTX64.EFI (fallback)" "$esp/EFI/BOOT/BOOTX64.EFI" "Microsoft"
  show_file "EFI/BOOT/grubx64.efi (fallback)" "$esp/EFI/BOOT/grubx64.efi" "Canonical"
  show_file "kernel" "$kernel" "Canonical"
  echo "Boot menu entries"
  { efibootmgr 2>/dev/null | grep -E 'BootOrder|BootCurrent|ubuntu|shim|MOX' | sed 's/^/  /'; } || true
  echo
  if [[ "$bad" == 0 ]]; then
    echo "Result: the boot chain is correctly signed."
    echo "If your PC still refuses it with Secure Boot on, its firmware doesn't trust Microsoft's third-party CA."
    echo "Look in BIOS for 'Microsoft UEFI CA', '3rd Party UEFI CA' or 'Reset Secure Boot keys to factory'."
  else
    echo "Result: the boot chain needs repair. Run: sudo mox secureboot fix"
  fi
  return "$bad"
}

fix() {
  [[ "$(id -u)" == 0 ]] || { echo "Run with sudo."; return 1; }
  [[ -d /sys/firmware/efi ]] || { echo "Start MOX in UEFI mode first."; return 1; }
  grep -q 'boot=casper' /proc/cmdline && { echo "This is the live USB. Start your installed MOX with Secure Boot off, then run this there."; return 1; }
  mountpoint -q "$esp" || mount "$esp" || { echo "Couldn't mount $esp."; return 1; }
  apt-get install -y shim-signed grub-efi-amd64-signed sbsigntool mokutil efibootmgr || return 1
  local backup="/boot/efi-backup-$(date +%Y%m%d-%H%M%S)"
  cp -a "$esp/EFI" "$backup" && echo "Old boot files saved to $backup"
  grub-install --target=x86_64-efi --efi-directory="$esp" --bootloader-id=ubuntu --uefi-secure-boot --force || return 1
  # PCs that only trust Microsoft's 2023 certificate need the dual-signed loader.
  if ! mokutil --db 2>/dev/null | grep -q "Microsoft Corporation UEFI CA 2011" && [[ -f /usr/lib/shim/shimx64.efi.dualsigned ]]; then
    cp /usr/lib/shim/shimx64.efi.dualsigned "$esp/EFI/ubuntu/shimx64.efi"
    echo "Using the dual-signed loader for this PC."
  fi
  mkdir -p "$esp/EFI/BOOT"
  cp "$esp/EFI/ubuntu/shimx64.efi" "$esp/EFI/BOOT/BOOTX64.EFI"
  cp "$esp/EFI/ubuntu/grubx64.efi" "$esp/EFI/ubuntu/mmx64.efi" "$esp/EFI/BOOT/"
  update-grub
  sync
  echo
  check && { echo; echo "Now restart, turn Secure Boot on in BIOS, and start MOX."; }
}

mok() {
  [[ "$(id -u)" == 0 ]] || { echo "Run with sudo."; return 1; }
  local file="${1:-}" dir=/root/.mox-secureboot
  [[ -f "$file" ]] || { echo "Usage: sudo mox secureboot mok FILE.efi"; return 1; }
  install -d -m 700 "$dir"
  if [[ ! -f "$dir/MOK.key" ]]; then
    openssl req -new -x509 -newkey rsa:2048 -nodes -days 3650 -sha256 -subj "/CN=MOX Machine Owner Key/" \
      -keyout "$dir/MOK.key" -out "$dir/MOK.crt" || return 1
    openssl x509 -in "$dir/MOK.crt" -outform DER -out "$dir/MOK.der" || return 1
    chmod 600 "$dir/MOK.key"
  fi
  sbsign --key "$dir/MOK.key" --cert "$dir/MOK.crt" --output "$file.signed" "$file" || return 1
  sbverify --cert "$dir/MOK.crt" "$file.signed" || return 1
  mv "$file.signed" "$file"
  mokutil --test-key "$dir/MOK.der" 2>&1 | grep -q "already enrolled" && { echo "Signed. This key is already enrolled."; return 0; }
  echo "Choose a one-time password. You'll type it once on the blue screen after restart."
  mokutil --import "$dir/MOK.der" || return 1
  echo "Restart, choose Enroll MOK, then Continue, Yes, and enter that password."
}

case "$action" in
  check) check ;;
  fix) fix ;;
  mok) mok "${2:-}" ;;
  *) echo "Usage: mox secureboot [check|fix|mok FILE.efi]"; exit 2 ;;
esac
