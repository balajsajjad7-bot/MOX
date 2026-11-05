# MOX

MOX is an open source operating system for developers and experts. It installs on a PC like Windows, and it is the father of Modo.

MOX is Linux based, with its own desktop, tools and update system.

## What's inside

| Area | Included |
|---|---|
| Desktop | Bottom dock, glass blur, 8 themes, live widgets, wallpapers that change through the day |
| Apps | MOX Browser, MOX Control, MOX Bot, This PC, MOX News, MOX TV, Shortwave radio, Modo, games, Spotify, Telegram, Discord and social app windows |
| Privacy | Tor windows for `.onion` sites, Tor Browser, SimpleX Chat, MOXWALL VPN and system-wide ad blocking |
| Protection | Firewall on by default, ClamAV, rootkit checks and signed updates |
| Hardware | Automatic drivers, Intel and NVIDIA support, printers, Bluetooth audio, optimizer and health report |
| Cloud | Google Drive and iCloud as drives |
| AI | `mox ai`, MOX Bot, Claude Code, Codex and local models |
| Home | Home Assistant through MOX Home |
| Mail | MOX Quantum Mail: post-quantum sealed messages and files, Geary mailbox, and your own mail server |
| Call center | MOX Dialer add-on, see `dialer/README.md` |
| Developer tools | C, C++, Python, Node, Go, Rust, Java, Docker, Podman, QEMU and security tools |

Security tools are for systems you own or have written permission to test.

## App support

| File | Layer | What to expect |
|---|---|---|
| Linux programs, `.deb`, AppImage, Flatpak | Native | Full support |
| `.exe`, `.msi` | Wine | Many apps work. Kernel drivers, Windows Store apps and strong anti-cheat usually don't |
| `.apk` | Waydroid (`mox get android`) | Good for light apps. Banking, payment and heavy game apps often fail |
| Mac `.app`, `.dmg`, `.pkg` | Darling (`mox get mac`) | Mostly command-line tools. GUI support is still in development |
| `.ipa` | touchHLE (`mox get iphone`) | Only unencrypted iPhone OS 2–3 apps, and many of those fail. Modern 64-bit apps can't run, and MOX explains why |

## Commands

```bash
mox status                     # layers and tools
mox hw                         # hardware report
mox drivers                    # find drivers
mox drivers --install          # install recommended drivers
mox drivers --ai               # ask AI about devices with no driver
mox ai key anthropic           # save a Claude API key
mox ai key openai              # save an OpenAI API key
mox ai why is my wifi slow     # ask anything
mox ai fix my sound is broken  # AI suggests commands, and you approve each set
mox get                        # list add-ons
mox get android                # install an add-on
mox connect add NAME URL       # add an MCP connector
mox update --check             # look for a signed update
sudo mox update                # install it
mox modo                       # open Modo
mox health                     # SSD and system health
mox optimize                   # tune MOX for this hardware
mox shield status              # firewall and antivirus
mox adblock status             # ad block
mox vpn make-server SERVER_IP  # create your own MOXWALL VPN
mox cloud add google           # add Google Drive
mox cloud add icloud           # add iCloud
mox theme frost                # change the look
mox wallpaper movie            # trending image with your own TMDB key
mox api add NAME               # save an API key in the vault
mox speed                      # test internet speed
mox fix                        # list problems the troubleshooter can repair
mox fix internet               # repair a problem, then ask AI if needed
mox power balanced             # choose a power plan
mox wifi                       # nearby networks and advice
mox wipe disk NAME             # permanently erase another drive
mox mail setup                 # create your post-quantum mail key
mox mail card ME@DOMAIN        # print your key card to share
mox mail add card.txt          # add a contact from their key card
mox mail seal --to A@B < msg   # seal a message for a contact
mox mail open < email.txt      # open a sealed message
mox mail dns DOMAIN SERVER_IP  # DNS records for your own mail server
mox get mailserver             # install the Stalwart mail server
sudo mox sync now              # get the newest MOX from GitHub
sudo mox sync on               # update automatically every hour
sudo mox secureboot            # check Secure Boot and every boot file
sudo mox secureboot fix        # repair the signed boot chain
mox tool add owner/name        # add an open source tool from GitHub
mox api free                   # APIs that need no key
mox bot                        # talk to MOX Bot
mox get dialer                 # install MOX Dialer
mox-run app.exe                # open any app file
```

## First-time setup for the creator

Do this once, on your own computer.

1. Make a public GitHub repository called `mox` and push this folder to it.
2. Create your signing key:

   ```bash
   tools/mox-keygen
   ```

3. Back up `~/.mox-keys/creator.key` offline. Never commit it or upload it. If you lose it, installed copies of MOX can't accept new updates. If someone else gets it, they can publish updates as you.
4. Commit `keys/creator.pub` and push.
5. In GitHub, open **Actions**, choose **Build MOX ISO** and press **Run workflow**. Or push a tag such as `v0.1.0` to publish a release.

## Installing MOX

Keep backups, and test on a spare PC or in a virtual machine first. In a virtual machine, turn on 3D acceleration. If the screen stays black on a machine with no working graphics driver, choose **MOX with software graphics** at the boot menu.

1. Download every `.part` file and join them.
   - Windows: `copy /b mox-0.1.0-amd64.iso.part00+mox-0.1.0-amd64.iso.part01+mox-0.1.0-amd64.iso.part02 mox-0.1.0-amd64.iso` (list every part you have)
   - Linux: `cat mox-*.part* > mox-0.1.0-amd64.iso`
2. Check that the file's SHA-256 matches the `.sha256` file.
3. Write the ISO to a USB drive of at least 16 GB with Rufus or balenaEtcher.
4. Boot from the USB drive and choose **Try or Install MOX**.
5. Open **Install MOX**. You need at least 40 GB of disk and 4 GB of RAM.

### Install from inside Windows, without a USB drive

1. Double-click the ISO. Windows opens it as a drive.
2. Open **Install MOX.cmd** and allow the administrator prompt.
3. Choose how much space MOX gets. The tool shrinks Windows, copies the installer to a 6 GB partition and restarts once into it.
4. In the MOX installer, choose **Replace a partition** and pick the free space. **Erase disk** deletes Windows.

This needs a 64-bit UEFI PC. Autorun no longer starts programs on its own in Windows, so you open the file yourself. To undo it before installing, run `mox-setup.ps1 -Remove` from the ISO as administrator.

Intel Macs can use **Install MOX.command** the same way. T2 Macs need Startup Security changed first, and their keyboard, WiFi and sound may not work. Apple silicon Macs can't run MOX.

## Privacy and erasing data

MOX offers full-disk encryption in the installer. Choose **Encrypt system** with a long passphrase. MOX keeps system logs in memory, has no hibernation file, and keeps crash dumps off the disk.

`sudo mox wipe disk NAME` erases another drive with the strongest method it supports. `sudo mox wipe keys NAME` destroys a LUKS drive's keys. `mox wipe file PATH` overwrites a file, but on SSDs that alone is not reliable.

No system can promise that recovery is impossible. A weak passphrase, a computer left running, malware, cloud copies and backups can all expose data.

## Quantum protection

MOX uses quantum-resistant methods where they exist today: MOX Quantum Mail, SimpleX Chat, preferred SSH key exchange, AES-256 disk encryption, and WireGuard preshared keys in MOXWALL. Web traffic depends on each website. Update signatures still use Ed25519.

## MOX Quantum Mail

MOX Mail seals messages and attachments with age 1.3 hybrid keys (ML-KEM-768 + X25519). The key exchange stays safe against a future quantum computer, and the message itself is encrypted with ChaCha20-Poly1305. Sealed text travels inside ordinary email, so Gmail, Outlook or your own server can carry it without being able to read it. Every sealed message is also sealed to you, so you can read what you sent.

1. Open **MOX Mail** and choose **Create key**. Back up `~/.local/share/mox/mail/identity.txt`. If you lose it, mail sealed to you can't be opened.
2. On **Contacts**, copy your key card and send it to people. Paste theirs to add them.
3. On **Write**, choose a contact, type, and press **Seal and copy**. Paste the result into any email. Use **Seal a file** for attachments.
4. On **Open**, paste a sealed email to read it.
5. **Mailbox** opens Geary for your normal email accounts.

For addresses on your own domain, run `sudo mox get mailserver` on a server with a public IP and port 25 open (many home connections block it), finish setup at `http://SERVER:8080/admin`, then add the records from `mox mail dns DOMAIN SERVER_IP` at your domain registrar. Stalwart can also encrypt stored mail at rest.

What it protects: the content of sealed messages and files. What it doesn't: the sender, recipients, subject line and timing, which every email system shows. Mail to people without MOX Mail is ordinary email, protected only by TLS between servers. Your key file on disk is as safe as your computer, so use full-disk encryption.

## Publishing an update

Only you can do this, because only you have the private key. Install the GitHub CLI, sign in, and run this from your repository on the computer that holds the key:

```bash
tools/mox-publish 0.2.0
git add -A && git commit -m "MOX 0.2.0" && git push
```

For more control, use the Owner Console on the same computer:

```bash
tools/mox-owner publish 0.3.0 10   # send to 10% of computers first
tools/mox-owner rollout 50         # widen to half
tools/mox-owner rollout 100        # everyone
tools/mox-owner pause              # stop a bad release everywhere
tools/mox-owner status
```

Every installed MOX checks every 6 hours, verifies your signature, installs the update, and tests that it still starts. If the test fails, it restores the old version. Ubuntu security updates and Flatpak apps also update automatically. To stop automatic MOX updates on one computer, create `/etc/mox/auto-update-off`.

Signed updates can do anything on every user's computer, so protect the key and test each release first.

## Building locally

Use Ubuntu 24.04 or newer, with about 40 GB of free disk:

```bash
sudo apt install mmdebstrap ubuntu-keyring squashfs-tools xorriso mtools dosfstools
sudo build/build-iso.sh
```

The ISO is written to `out/`. Set `MOX_SQUASHFS_COMP=zstd` for a faster build and a larger ISO.

## Tests

```bash
python3 -m unittest tests/test_mox.py
```

## Project layout

```text
overlay/          files copied into the system
build/            ISO build, package lists, installer settings
branding/         logo and wallpaper sources
tools/            signing key and release tools
tests/            automated tests
```

## Licence

GPL-3.0-or-later for MOX's own code. Ubuntu, GNOME and the bundled tools keep their own licences. Anyone may read or fork the code, but only releases signed with the creator's key reach official MOX installs. The owner of a machine still has full control of their own copy.
