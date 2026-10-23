"""Compare a folder with its backup. Read-only: nothing is ever written, moved or deleted.

Quick check   compares names, sizes and modification times.
Sample check  also reads a random sample of matching files on both sides and compares their contents.
Deep check    reads every matching file on both sides (SHA-256), which catches silent corruption.
"""
from __future__ import annotations

import fnmatch
import hashlib
import os
import random
import stat
import time
from dataclasses import dataclass, field

REPARSE_POINT = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
DEFAULT_IGNORE = ("Thumbs.db", "desktop.ini", ".DS_Store", "~$*", "*.tmp")
CHUNK = 1 << 20


@dataclass
class Entry:
    path: str      # relative, original case
    size: int
    mtime: float


@dataclass
class Result:
    source: str
    backup: str
    mode: str
    files_checked: int = 0
    bytes_checked: int = 0
    missing: list[Entry] = field(default_factory=list)        # in source, not in backup
    extra: list[Entry] = field(default_factory=list)          # in backup only (often fine: old files kept)
    outdated: list[tuple[Entry, Entry]] = field(default_factory=list)   # source changed since the backup
    differs: list[tuple[Entry, Entry]] = field(default_factory=list)    # same size/time, different content
    unreadable: list[str] = field(default_factory=list)
    links_skipped: int = 0
    contents_verified: int = 0
    seconds: float = 0.0

    @property
    def ok(self) -> bool:
        return not (self.missing or self.outdated or self.differs or self.unreadable)

    def headline(self) -> str:
        if self.ok:
            checked = f", contents of {self.contents_verified} files verified" if self.contents_verified else ""
            return f"Backup OK: all {self.files_checked:,} files are present and current{checked}."
        parts = []
        if self.missing:
            parts.append(f"{len(self.missing):,} missing")
        if self.outdated:
            parts.append(f"{len(self.outdated):,} out of date")
        if self.differs:
            parts.append(f"{len(self.differs):,} with different contents (possible corruption)")
        if self.unreadable:
            parts.append(f"{len(self.unreadable):,} unreadable")
        return "Backup has problems: " + ", ".join(parts) + "."


def _ignored(name: str, patterns) -> bool:
    return any(fnmatch.fnmatch(name.lower(), p.lower()) for p in patterns)


def index(root: str, ignore=DEFAULT_IGNORE, should_stop=None, errors: list | None = None) -> tuple[dict, int]:
    """{lower-case relative path: Entry}, and how many links/junctions were skipped (never followed)."""
    found: dict[str, Entry] = {}
    links = 0
    stack = [root]
    while stack:
        if should_stop and should_stop():
            break
        folder = stack.pop()
        try:
            entries = list(os.scandir(folder))
        except OSError as exc:
            if errors is not None:
                errors.append(f"{os.path.relpath(folder, root)}: {exc.strerror or exc}")
            continue
        for entry in entries:
            try:
                info = entry.stat(follow_symlinks=False)
                if entry.is_symlink() or getattr(info, "st_file_attributes", 0) & REPARSE_POINT:
                    links += 1
                    continue
                if _ignored(entry.name, ignore):
                    continue
                if entry.is_dir(follow_symlinks=False):
                    stack.append(entry.path)
                else:
                    relative = os.path.relpath(entry.path, root)
                    found[relative.lower()] = Entry(relative, info.st_size, info.st_mtime)
            except OSError as exc:
                if errors is not None:
                    errors.append(f"{os.path.relpath(entry.path, root)}: {exc.strerror or exc}")
    return found, links


def file_hash(path: str, should_stop=None) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while True:
            if should_stop and should_stop():
                raise InterruptedError
            block = handle.read(CHUNK)
            if not block:
                return digest.hexdigest()
            digest.update(block)


def _same_time(a: float, b: float, tolerance: float, dst_shift: bool) -> bool:
    delta = abs(a - b)
    return delta <= tolerance or (dst_shift and abs(delta - 3600) <= tolerance)


def verify(source: str, backup: str, *, mode: str = "quick", sample_percent: float = 5.0,
           ignore=DEFAULT_IGNORE, time_tolerance: float = 2.0, dst_shift: bool = True, seed: int | None = None,
           progress=None, should_stop=None) -> Result:
    """mode: quick | sample | deep. time_tolerance covers FAT/exFAT's 2-second timestamps; dst_shift accepts the
    one-hour offsets some copy tools and FAT drives show after a daylight-saving change."""
    if mode not in ("quick", "sample", "deep"):
        raise ValueError("mode must be quick, sample or deep")
    for folder, label in ((source, "source"), (backup, "backup")):
        if not os.path.isdir(folder):
            raise FileNotFoundError(f"{label} folder not found: {folder}")
    started = time.monotonic()
    result = Result(os.path.abspath(source), os.path.abspath(backup), mode)
    errors: list[str] = []
    src, src_links = index(source, ignore, should_stop, errors)
    dst, dst_links = index(backup, ignore, should_stop, errors)
    result.unreadable.extend(errors)
    result.links_skipped = src_links + dst_links
    matching: list[tuple[Entry, Entry]] = []
    for key, a in src.items():
        result.files_checked += 1
        result.bytes_checked += a.size
        b = dst.get(key)
        if b is None:
            result.missing.append(a)
        elif a.size != b.size or not _same_time(a.mtime, b.mtime, time_tolerance, dst_shift):
            if a.size == b.size and a.mtime < b.mtime:
                matching.append((a, b))  # backup copied later with the same size: compare contents to be sure
            else:
                result.outdated.append((a, b))
        else:
            matching.append((a, b))
    result.extra = [e for k, e in dst.items() if k not in src]
    if mode != "quick" and matching:
        chosen = matching
        if mode == "sample":
            count = max(1, round(len(matching) * sample_percent / 100))
            chosen = random.Random(seed).sample(matching, min(count, len(matching)))
        for done, (a, b) in enumerate(chosen, 1):
            if should_stop and should_stop():
                break
            try:
                same = file_hash(os.path.join(source, a.path), should_stop) == \
                    file_hash(os.path.join(backup, b.path), should_stop)
            except InterruptedError:
                break
            except OSError as exc:
                result.unreadable.append(f"{a.path}: {exc.strerror or exc}")
                continue
            result.contents_verified += 1
            if not same:
                result.differs.append((a, b))
            if progress and done % 25 == 0:
                progress(done, len(chosen), a.path)
    for bucket in (result.missing, result.extra):
        bucket.sort(key=lambda e: e.path.lower())
    result.seconds = round(time.monotonic() - started, 2)
    return result
