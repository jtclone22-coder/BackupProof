# Changelog

## 0.1.1 (2026-10-24)

Fixes from a code review.

- Stopping a check no longer reports "Backup OK": a stopped check is incomplete and says so (before, a backup with corrupted files could show as OK if you pressed Stop during a Sample or Deep check).
- Ignore patterns such as `*.tmp` apply to files only; a folder whose name matches is still checked.

## 0.1.0 (2026-10-22)

- Quick, sample and deep (SHA-256) checks: missing, out-of-date and content-differs files, plus files only in the backup.
- Tolerates FAT timestamps and daylight-saving shifts; case-insensitive; default ignores; never follows links.
- Saved jobs, a run-all command with exit codes, history, HTML and CSV reports, a command line and a window.
