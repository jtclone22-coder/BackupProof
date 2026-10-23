"""HTML and CSV reports of a check, plus saved jobs and history (%APPDATA%\\BackupProof)."""
from __future__ import annotations

import csv
import html
import json
import os
import time
from pathlib import Path

from .verify import Result


def home() -> Path:
    base = os.environ.get("BACKUPPROOF_HOME") or (
        os.path.join(os.environ["APPDATA"], "BackupProof") if os.environ.get("APPDATA")
        else os.path.join(os.path.expanduser("~"), ".backupproof"))
    Path(base).mkdir(parents=True, exist_ok=True)
    return Path(base)


def load_jobs() -> list[dict]:
    try:
        return json.loads((home() / "jobs.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def save_jobs(jobs: list[dict]) -> None:
    (home() / "jobs.json").write_text(json.dumps(jobs, indent=2), encoding="utf-8")


def record(result: Result) -> None:
    line = {"time": time.strftime("%Y-%m-%d %H:%M"), "source": result.source, "backup": result.backup,
            "mode": result.mode, "ok": result.ok, "summary": result.headline()}
    with (home() / "history.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(line) + "\n")


def history(limit: int = 20) -> list[dict]:
    try:
        lines = (home() / "history.jsonl").read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    return [json.loads(line) for line in lines[-limit:]]


def rows(result: Result) -> list[tuple[str, str, str]]:
    out = [("missing from backup", e.path, f"{e.size:,} bytes") for e in result.missing]
    out += [("out of date in backup", a.path, f"source {time.strftime('%Y-%m-%d %H:%M', time.localtime(a.mtime))}, "
             f"backup {time.strftime('%Y-%m-%d %H:%M', time.localtime(b.mtime))}") for a, b in result.outdated]
    out += [("contents differ", a.path, "same size and date, different data") for a, b in result.differs]
    out += [("unreadable", item, "") for item in result.unreadable]
    out += [("only in backup", e.path, f"{e.size:,} bytes") for e in result.extra]
    return out


def write_csv(result: Result, path: Path) -> Path:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["problem", "file", "detail"])
        writer.writerows(rows(result))
    return path


def write_html(result: Result, path: Path) -> Path:
    color = "#1f7a3a" if result.ok else "#b91c1c"
    body = "".join(f"<tr><td>{html.escape(k)}</td><td>{html.escape(f)}</td><td>{html.escape(d)}</td></tr>"
                   for k, f, d in rows(result)[:5000])
    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>BackupProof report</title>
<style>body{{font:15px/1.5 'Segoe UI',system-ui,sans-serif;max-width:1000px;margin:24px auto;padding:0 16px;color:#1b1f24}}
.v{{border-left:6px solid {color};background:#f6f6f7;padding:12px 16px}} table{{border-collapse:collapse;width:100%;font-size:13px}}
td,th{{text-align:left;border-bottom:1px solid #e3e3e3;padding:5px 7px;vertical-align:top}} th{{background:#f1f2f4}}</style></head>
<body><h1>BackupProof report</h1><div class="v"><strong style="color:{color}">{html.escape(result.headline())}</strong>
<p>Source: {html.escape(result.source)}<br>Backup: {html.escape(result.backup)}<br>
Check: {result.mode}, {result.files_checked:,} files ({result.bytes_checked / 1e9:.2f} GB), {result.seconds}s,
{time.strftime('%Y-%m-%d %H:%M')}. Links and junctions skipped: {result.links_skipped}.</p></div>
<h2>Details</h2><table><tr><th>Problem</th><th>File</th><th>Detail</th></tr>{body}</table>
<p style="color:#666;font-size:13px">"Only in backup" is usually fine (older files a mirror keeps). Read-only check: nothing was changed.</p>
</body></html>"""
    path.write_text(page, encoding="utf-8")
    return path
