# BackupProof

**Don't trust a backup you haven't checked.** BackupProof compares a folder with its backup and tells you, in plain words, what's missing, what's out of date and, with a deep check, which files have silently corrupted. It is read-only and never changes a file.

Real result on the developer's own PC: the backup copy of a 3D project was missing **1,470 files (3.8 GB)**, everything from the last four days of work. The backup script had simply not run since then.

## Download

Get **BackupProof-0.1.0-windows.zip** from [Releases](../../releases/latest), unzip it anywhere and double-click **BackupProof.exe** in the BackupProof folder. Nothing to install, and no Python needed.

Windows may say "Windows protected your PC" because the app is new: click **More info**, then **Run anyway**.

Prefer Python? With Python 3.9 or newer, download this repository and run `py -m backupproof` in its folder.

## Checks

| Check | What it compares | Speed |
|---|---|---|
| **Quick** | Names, sizes and modification dates | Seconds, even for big folders |
| **Sample** | Quick, plus the actual contents of a random 5% of files on both sides | A good confidence check |
| **Deep** | Every file's contents (SHA-256) on both sides | Slow, but catches silent corruption ("bit rot") and bad copies |

**Built for real backups:**
- It tolerates FAT/exFAT's 2-second timestamps and the one-hour shift some drives show after daylight saving.
- It ignores case differences on Windows, and skips `Thumbs.db`, `desktop.ini` and Office lock files.
- It never follows junctions or symlinks.
- Files that exist only in the backup are listed but are not counted as problems, since mirrors often keep old files.
- **Saved jobs and history.** `run` checks every saved job and exits with code 1 when something is wrong, so it can run from Task Scheduler.
- **HTML and CSV reports.**

## Use it

Double-click `BackupProof.bat`, choose the original folder and its backup, and press **Quick check**.

```
py -m backupproof check "D:\Photos" "E:\Backup\Photos"
py -m backupproof check "D:\Projects" "\nas\backup\Projects" --mode deep --html report.html
py -m backupproof add "D:\Photos" "E:\Backup\Photos" --name photos
py -m backupproof run --mode sample
py -m backupproof history
```

## Tests
```
py -m unittest discover -s tests
```

MIT License.
