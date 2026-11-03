#!/usr/bin/env bash
# Builds the MOX installer ISO. Run as root on Ubuntu with the packages in README.md.
set -euo pipefail
repo="$(cd "$(dirname "$0")/.." && pwd)"
work="${MOX_WORK:-$repo/work}"
out="${MOX_OUT:-$repo/out}"
comp="${MOX_SQUASHFS_COMP:-xz}"
version="$(cat "$repo/overlay/usr/lib/mox/VERSION")"
root="$work/rootfs"
iso="$work/iso"

[[ $EUID -eq 0 ]] || { echo "Run as root." >&2; exit 1; }
[[ -f "$repo/keys/creator.pub" ]] || { echo "keys/creator.pub is missing. Run tools/mox-keygen first." >&2; exit 1; }

cleanup() {
  for mount in dev/pts dev proc sys run; do umount -lf "$root/$mount" 2>/dev/null || true; done
}
trap cleanup EXIT

step() { printf '\n=== %s (%s)\n' "$1" "$(date +%H:%M:%S)"; }

if [[ "${MOX_RESUME:-0}" == 0 ]]; then
  step "Creating base system"
  rm -rf "$root" "$iso"
  mkdir -p "$work" "$out"
  mmdebstrap --variant=minbase --components=main,universe \
    --include=ubuntu-keyring,ca-certificates,apt,gpgv,dialog,debconf \
    resolute "$root" http://archive.ubuntu.com/ubuntu/

  step "Adding MOX files"
  cp -a "$repo/overlay/." "$root/"
  cp -a "$repo/dialer" "$root/usr/lib/mox/dialer"
  cp "$repo/keys/creator.pub" "$root/usr/share/mox/keys/creator.pub"
  grep -hv '^#' "$repo"/build/packages/*.list | sort -u > "$root/tmp/mox-packages.list"
  cp "$repo/build/chroot-setup.sh" "$root/tmp/mox-setup.sh"
  mkdir -p "$root/etc/calamares"
  cp -a "$repo/build/calamares/." "$root/etc/calamares/"
  [[ -z "${MOX_EXTRA_CA:-}" ]] || cp "$MOX_EXTRA_CA" "$root/tmp/mox-ca.crt"

  step "Installing packages"
  mount --bind /dev "$root/dev"
  mount --bind /dev/pts "$root/dev/pts"
  mount -t proc proc "$root/proc"
  mount -t sysfs sys "$root/sys"
  mount -t tmpfs tmpfs "$root/run"
  rm -f "$root/etc/resolv.conf"
  cp -L /etc/resolv.conf "$root/etc/resolv.conf"
  chroot "$root" /bin/bash /tmp/mox-setup.sh
  rm -f "$root/etc/resolv.conf"
  ln -s ../run/systemd/resolve/stub-resolv.conf "$root/etc/resolv.conf"
  cleanup
fi

step "Building boot files"
# MOX_RESUME=2 reuses a finished compressed system.
if [[ "${MOX_RESUME:-0}" == 2 ]]; then mv "$iso/casper/filesystem.squashfs" "$work/keep.squashfs"; fi
rm -rf "$iso"
mkdir -p "$iso/casper" "$iso/boot/grub" "$iso/.disk" "$out"
kernel="$(ls -1 "$root"/boot/vmlinuz-* | sort -V | tail -1)"
cp "$kernel" "$iso/casper/vmlinuz"
cp "$root/boot/initrd.img-${kernel##*vmlinuz-}" "$iso/casper/initrd"
echo "MOX $version" > "$iso/.disk/info"
du -sx --block-size=1 "$root" | cut -f1 > "$iso/casper/filesystem.size"
cat > "$iso/boot/grub/grub.cfg" <<GRUB
set timeout=5
set default=0
insmod all_video
set menu_color_highlight=white/magenta
menuentry "Try or Install MOX" {
  linux /casper/vmlinuz boot=casper nopersistent quiet splash ---
  initrd /casper/initrd
}
menuentry "MOX in safe graphics mode" {
  linux /casper/vmlinuz boot=casper nopersistent nomodeset ---
  initrd /casper/initrd
}
menuentry "MOX with software graphics (slow, for machines without a graphics driver)" {
  linux /casper/vmlinuz boot=casper nopersistent mox.softgl ---
  initrd /casper/initrd
}
GRUB

cat > "$root/tmp/embed.cfg" <<GRUB
search --no-floppy --set=root --file /casper/vmlinuz
set prefix=(\$root)/boot/grub
configfile /boot/grub/grub.cfg
GRUB
chroot "$root" grub-mkstandalone --format=i386-pc --output=/tmp/core.img \
  --install-modules="linux normal iso9660 biosdisk memdisk search tar ls all_video configfile gfxterm" \
  --modules="linux normal iso9660 biosdisk search configfile" \
  --locales="" --fonts="" "boot/grub/grub.cfg=/tmp/embed.cfg"
cat "$root/usr/lib/grub/i386-pc/cdboot.img" "$root/tmp/core.img" > "$iso/boot/bios.img"
cp "$root/usr/lib/grub/i386-pc/boot_hybrid.img" "$work/boot_hybrid.img"
rm -f "$root/tmp/core.img" "$root/tmp/embed.cfg"

efi="$work/efi.img"
shim="$root/usr/lib/shim/shimx64.efi.signed.latest"   # .previous is revoked by SBAT
rm -f "$efi"
truncate -s 16M "$efi"
mkfs.vfat -n MOXEFI "$efi" >/dev/null
mmd -i "$efi" ::/EFI ::/EFI/BOOT
mcopy -i "$efi" "$shim" ::/EFI/BOOT/BOOTX64.EFI
mcopy -i "$efi" "$root/usr/lib/grub/x86_64-efi-signed/gcdx64.efi.signed" ::/EFI/BOOT/grubx64.efi
mcopy -i "$efi" "$root/usr/lib/shim/mmx64.efi" ::/EFI/BOOT/mmx64.efi

# Lets the ISO's contents boot from a FAT32 partition, for installing from inside Windows or macOS
mkdir -p "$iso/EFI/BOOT"
cp "$shim" "$iso/EFI/BOOT/BOOTX64.EFI"
cp "$root/usr/lib/grub/x86_64-efi-signed/gcdx64.efi.signed" "$iso/EFI/BOOT/grubx64.efi"
cp "$root/usr/lib/shim/mmx64.efi" "$iso/EFI/BOOT/mmx64.efi"
cp -a "$repo/build/iso-root/." "$iso/"

step "Compressing the system ($comp)"
if [[ "${MOX_RESUME:-0}" == 2 ]]; then
  mv "$work/keep.squashfs" "$iso/casper/filesystem.squashfs"
else
  extra=()
  [[ "$comp" != xz ]] || extra=(-b 1M -Xbcj x86)
  mksquashfs "$root" "$iso/casper/filesystem.squashfs" -noappend -comp "$comp" "${extra[@]}" -e boot/grub -wildcards -e 'var/cache/apt/archives/*.deb'
fi

squash_size="$(stat -c %s "$iso/casper/filesystem.squashfs")"
(( squash_size < 4294967296 )) || echo "WARNING: system image is over 4 GiB, so direct install from Windows will refuse it"

step "Writing ISO"
target="$out/mox-$version-amd64.iso"
xorriso -as mkisofs -r -V "MOX_$(tr -d . <<<"$version")" -o "$target" -iso-level 3 -J -joliet-long \
  --grub2-mbr "$work/boot_hybrid.img" -partition_offset 16 \
  -append_partition 2 0xef "$efi" -appended_part_as_gpt \
  -c boot/boot.cat -b boot/bios.img -no-emul-boot -boot-load-size 4 -boot-info-table --grub2-boot-info \
  -eltorito-alt-boot -e --interval:appended_partition_2:all:: -no-emul-boot \
  "$iso"
sha256sum "$target" > "$target.sha256"
ls -lh "$target"
