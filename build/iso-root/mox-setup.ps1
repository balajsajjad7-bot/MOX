# MOX Installer for Windows. Double-click "Install MOX.cmd" on the mounted ISO.
# Makes room on the disk, copies the MOX installer there, and restarts into it once.
# Windows stays in place until you choose otherwise in the MOX installer.
# Use -Remove to undo this before installing.
param([switch]$Remove)
$ErrorActionPreference = 'Stop'
$LiveGB = 6
$Label = 'MOXLIVE'

function Stop-Setup($message) { Write-Host "`n$message" -ForegroundColor Yellow; Read-Host 'Press Enter to close' | Out-Null; exit 1 }

$me = [Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
if (-not $me.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
  $flags = "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`""
  if ($Remove) { $flags += ' -Remove' }
  Start-Process powershell -Verb RunAs -ArgumentList $flags
  exit
}

$live = Get-Volume | Where-Object { $_.FileSystemLabel -eq $Label } | Select-Object -First 1
$systemDrive = $env:SystemDrive.TrimEnd(':')

if ($Remove) {
  if (-not $live) { Stop-Setup 'The MOX installer is not on this PC.' }
  $line = (bcdedit /enum firmware | Select-String -Context 3,0 'MOX Installer' | Select-Object -First 1)
  if ($line) {
    $id = [regex]::Match(($line.Context.PreContext -join ' '), '\{[0-9a-fA-F-]{36}\}').Value
    if ($id) { bcdedit /delete $id | Out-Null }
  }
  Remove-Partition -DriveLetter $live.DriveLetter -Confirm:$false
  $max = (Get-PartitionSupportedSize -DriveLetter $systemDrive).SizeMax
  Resize-Partition -DriveLetter $systemDrive -Size $max
  Write-Host 'Removed. Your disk space is back.' -ForegroundColor Green
  Read-Host 'Press Enter to close' | Out-Null
  exit 0
}

Write-Host "`n  M O X`n"
if (-not [Environment]::Is64BitOperatingSystem) { Stop-Setup 'MOX needs a 64-bit PC.' }
if ((bcdedit /enum '{current}' | Out-String) -notmatch 'winload\.efi') {
  Stop-Setup 'This PC starts in Legacy BIOS mode. Install MOX from a USB drive instead.'
}
if ($live) { Stop-Setup 'The MOX installer is already on this PC. Run with -Remove to undo it.' }
foreach ($file in 'casper\filesystem.squashfs', 'casper\vmlinuz', 'EFI\BOOT\BOOTX64.EFI') {
  if (-not (Test-Path (Join-Path $PSScriptRoot $file))) { Stop-Setup 'Open this from the mounted MOX ISO.' }
}
if ((Get-Item (Join-Path $PSScriptRoot 'casper\filesystem.squashfs')).Length -ge 4GB) {
  Stop-Setup 'This ISO is too large for direct install. Use a USB drive.'
}

$size = (Get-PartitionSupportedSize -DriveLetter $systemDrive)
$current = (Get-Partition -DriveLetter $systemDrive).Size
$canFree = [math]::Floor(($current - $size.SizeMin) / 1GB) - 25
if ($canFree -lt (40 + $LiveGB)) { Stop-Setup "Only $canFree GB can be freed on $systemDrive`:. MOX needs at least $(40 + $LiveGB) GB." }
$default = [math]::Min(100, $canFree - $LiveGB)
Write-Host "How much disk space should MOX get? Windows keeps the rest."
$answer = Read-Host "Size in GB, 40 to $($canFree - $LiveGB) [$default]"
$moxGB = if ($answer) { [int]$answer } else { $default }
if ($moxGB -lt 40 -or $moxGB -gt ($canFree - $LiveGB)) { Stop-Setup 'That size is out of range.' }

Write-Host "`nThis will:"
Write-Host "  - shrink $systemDrive`: by $($moxGB + $LiveGB) GB (your files stay)"
Write-Host "  - copy the MOX installer to the disk"
Write-Host "  - restart once into the MOX installer"
Write-Host "`nBack up important files first. Plug in the charger on a laptop."
$bitlocker = Get-BitLockerVolume -MountPoint "$systemDrive`:" -ErrorAction SilentlyContinue
if ($bitlocker -and $bitlocker.ProtectionStatus -eq 'On') {
  Write-Host "`nBitLocker is on. Make sure you have your recovery key before you go on." -ForegroundColor Yellow
}
if ((Read-Host "`nType YES to continue") -ne 'YES') { Stop-Setup 'Nothing was changed.' }

Write-Host "`nMaking room..."
Resize-Partition -DriveLetter $systemDrive -Size ($current - (($moxGB + $LiveGB) * 1GB))
$disk = (Get-Partition -DriveLetter $systemDrive).DiskNumber
$part = New-Partition -DiskNumber $disk -Size ($LiveGB * 1GB) -AssignDriveLetter
Format-Volume -Partition $part -FileSystem FAT32 -NewFileSystemLabel $Label -Force -Confirm:$false | Out-Null
$target = "$($part.DriveLetter):\"

Write-Host 'Copying MOX. This takes a few minutes...'
robocopy $PSScriptRoot $target /E /R:2 /W:2 /NFL /NDL /NJH /NP /XF autorun.inf | Out-Null
if ($LASTEXITCODE -ge 8) { Stop-Setup 'Copying failed. Run this with -Remove, then try again.' }

$created = bcdedit /copy '{bootmgr}' /d 'MOX Installer'
$id = [regex]::Match(($created -join ' '), '\{[0-9a-fA-F-]{36}\}').Value
if (-not $id) { Stop-Setup "Couldn't add the MOX boot entry. Run this with -Remove." }
bcdedit /set $id device "partition=$($part.DriveLetter):" | Out-Null
bcdedit /set $id path '\EFI\BOOT\BOOTX64.EFI' | Out-Null
bcdedit /set '{fwbootmgr}' bootsequence $id | Out-Null
if ($bitlocker -and $bitlocker.ProtectionStatus -eq 'On') {
  manage-bde -protectors -disable "$systemDrive`:" -RebootCount 2 | Out-Null
}

Write-Host "`nReady. In the MOX installer, choose 'Replace a partition' and pick the free space." -ForegroundColor Green
Write-Host "Don't choose 'Erase disk' unless you want to delete Windows."
Read-Host "`nPress Enter to restart"
shutdown /r /t 3
