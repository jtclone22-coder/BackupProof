"""BackupProof tests on temporary folders (read-only checks; the tests only write their own temp files)."""
from __future__ import annotations

import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backupproof import report  # noqa: E402
from backupproof.verify import verify  # noqa: E402

try:
    import _winapi
    HAS_JUNCTIONS = hasattr(_winapi, "CreateJunction")
except ImportError:
    HAS_JUNCTIONS = False


def write(path: Path, data: bytes, mtime: float | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    if mtime is not None:
        os.utime(path, (mtime, mtime))


class Pair(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.src = Path(self.temp.name) / "src"
        self.dst = Path(self.temp.name) / "dst"
        self.t0 = time.time() - 86400
        for rel, data in (("a.txt", b"alpha"), ("docs/b.txt", b"bravo"), ("docs/deep/c.bin", b"charlie" * 100)):
            write(self.src / rel, data, self.t0)
            write(self.dst / rel, data, self.t0)
        os.environ["BACKUPPROOF_HOME"] = str(Path(self.temp.name) / "home")
        self.addCleanup(os.environ.pop, "BACKUPPROOF_HOME", None)


class VerifyTests(Pair):
    def test_identical_backup_is_ok_in_every_mode(self) -> None:
        for mode in ("quick", "sample", "deep"):
            result = verify(str(self.src), str(self.dst), mode=mode, sample_percent=100)
            self.assertTrue(result.ok, (mode, result.headline()))
            self.assertEqual(result.files_checked, 3)
        self.assertEqual(verify(str(self.src), str(self.dst), mode="deep").contents_verified, 3)

    def test_finds_missing_outdated_and_extra(self) -> None:
        write(self.src / "new.txt", b"not backed up yet")
        write(self.src / "a.txt", b"alpha v2, longer", self.t0 + 600)
        write(self.dst / "old-only.txt", b"kept by the mirror")
        result = verify(str(self.src), str(self.dst))
        self.assertFalse(result.ok)
        self.assertEqual([e.path for e in result.missing], ["new.txt"])
        self.assertEqual([a.path for a, _ in result.outdated], ["a.txt"])
        self.assertEqual([e.path for e in result.extra], ["old-only.txt"])
        self.assertIn("1 missing, 1 out of date", result.headline())

    def test_deep_check_catches_silent_corruption(self) -> None:
        write(self.dst / "docs/deep/c.bin", b"charliX" + b"charlie" * 99, self.t0)  # same size, same date
        self.assertTrue(verify(str(self.src), str(self.dst), mode="quick").ok)  # quick can't see it
        deep = verify(str(self.src), str(self.dst), mode="deep")
        self.assertEqual([a.path for a, _ in deep.differs], [os.path.join("docs", "deep", "c.bin")])
        self.assertIn("possible corruption", deep.headline())

    def test_sample_mode_is_reproducible_with_a_seed(self) -> None:
        for index in range(40):
            write(self.src / "many" / f"{index}.txt", str(index).encode(), self.t0)
            write(self.dst / "many" / f"{index}.txt", str(index).encode(), self.t0)
        one = verify(str(self.src), str(self.dst), mode="sample", sample_percent=10, seed=7)
        two = verify(str(self.src), str(self.dst), mode="sample", sample_percent=10, seed=7)
        self.assertEqual(one.contents_verified, two.contents_verified)
        self.assertEqual(one.contents_verified, 4)  # 10% of 43 files, rounded

    def test_timestamps_case_and_ignored_files(self) -> None:
        write(self.dst / "a.txt", b"alpha", self.t0 + 1)          # FAT/exFAT 2-second resolution
        write(self.src / "docs/b.txt", b"bravo", self.t0 + 3600)  # DST one-hour shift (original looks newer)
        (self.dst / "docs" / "deep" / "c.bin").rename(self.dst / "docs" / "deep" / "C.BIN")  # Windows case
        write(self.src / "Thumbs.db", b"noise")
        write(self.src / "~$report.docx", b"office lock file")
        result = verify(str(self.src), str(self.dst))
        self.assertTrue(result.ok, result.headline())
        strict = verify(str(self.src), str(self.dst), dst_shift=False)
        self.assertEqual([a.path for a, _ in strict.outdated], [os.path.join("docs", "b.txt")])

    def test_newer_backup_copy_with_same_size_is_checked_not_flagged(self) -> None:
        write(self.dst / "a.txt", b"alpha", self.t0 + 9000)
        self.assertTrue(verify(str(self.src), str(self.dst)).ok)
        write(self.dst / "a.txt", b"alphX", self.t0 + 9000)
        self.assertEqual(len(verify(str(self.src), str(self.dst), mode="deep").differs), 1)

    @unittest.skipUnless(HAS_JUNCTIONS, "junctions need Windows")
    def test_junctions_are_not_followed(self) -> None:
        elsewhere = Path(self.temp.name) / "elsewhere"
        write(elsewhere / "huge.bin", b"x" * 1000)
        _winapi.CreateJunction(str(elsewhere), str(self.src / "linked"))
        result = verify(str(self.src), str(self.dst))
        self.assertTrue(result.ok)
        self.assertEqual(result.links_skipped, 1)

    def test_missing_folder_and_bad_mode(self) -> None:
        with self.assertRaises(FileNotFoundError):
            verify(str(self.src), str(self.dst / "nope"))
        with self.assertRaises(ValueError):
            verify(str(self.src), str(self.dst), mode="fast")


class ReportTests(Pair):
    def test_reports_jobs_and_history(self) -> None:
        write(self.src / "R&D notes.txt", b"x")
        result = verify(str(self.src), str(self.dst))
        page = report.write_html(result, Path(self.temp.name) / "r.html").read_text(encoding="utf-8")
        self.assertIn("R&amp;D notes.txt", page)
        self.assertIn("missing from backup", report.write_csv(result, Path(self.temp.name) / "r.csv").read_text())
        report.record(result)
        self.assertFalse(report.history()[-1]["ok"])
        report.save_jobs([{"name": "docs", "source": str(self.src), "backup": str(self.dst)}])
        self.assertEqual(report.load_jobs()[0]["name"], "docs")


if __name__ == "__main__":
    unittest.main()
