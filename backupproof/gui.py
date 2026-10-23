"""Window: pick a folder and its backup (or a saved job), run a quick, sample or deep check, see what's wrong."""
from __future__ import annotations

import os
import queue
import sys
import tempfile
import threading
from pathlib import Path

from . import __version__, report
from .verify import verify


def main() -> int:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk

    root = tk.Tk()
    root.title(f"BackupProof {__version__}")
    root.geometry("980x620")
    messages: queue.Queue = queue.Queue()
    stop = threading.Event()
    state = {"result": None}

    form = ttk.Frame(root, padding=10)
    form.pack(fill="x")
    source, backup = tk.StringVar(), tk.StringVar()
    for row, (label, var) in enumerate((("Original folder", source), ("Backup folder", backup))):
        ttk.Label(form, text=label).grid(row=row, column=0, sticky="w")
        ttk.Entry(form, textvariable=var, width=80).grid(row=row, column=1, padx=6, pady=2, sticky="we")
        ttk.Button(form, text="Browse…", command=lambda v=var: v.set(filedialog.askdirectory() or v.get())).grid(
            row=row, column=2)
    jobs = report.load_jobs()
    job_pick = ttk.Combobox(form, state="readonly", width=40, values=[j["name"] for j in jobs])
    ttk.Label(form, text="Saved job").grid(row=2, column=0, sticky="w")
    job_pick.grid(row=2, column=1, sticky="w", padx=6)

    def use_job(_event=None) -> None:
        job = jobs[job_pick.current()]
        source.set(job["source"])
        backup.set(job["backup"])

    job_pick.bind("<<ComboboxSelected>>", use_job)

    def save_job() -> None:
        if source.get() and backup.get():
            jobs.append({"name": Path(source.get()).name, "source": source.get(), "backup": backup.get()})
            report.save_jobs(jobs)
            job_pick.configure(values=[j["name"] for j in jobs])

    ttk.Button(form, text="Save as job", command=save_job).grid(row=2, column=2)
    buttons = ttk.Frame(root, padding=(10, 0))
    buttons.pack(fill="x")
    headline = tk.Label(root, text="Quick compares names, sizes and dates. Sample reads 5% of files on both sides. "
                                   "Deep reads everything (slow, catches silent corruption).",
                        font=("Segoe UI", 11, "bold"), anchor="w", justify="left", wraplength=940)
    headline.pack(fill="x", padx=10, pady=8)
    tree = ttk.Treeview(root, columns=("problem", "file", "detail"), show="headings")
    for column, width in (("problem", 170), ("file", 480), ("detail", 280)):
        tree.heading(column, text=column.title())
        tree.column(column, width=width)
    tree.pack(fill="both", expand=True, padx=10)
    status = ttk.Label(root, text="Read-only: BackupProof never changes your files.", anchor="w")
    status.pack(fill="x", padx=10, pady=6)

    def start(mode: str) -> None:
        if not (source.get() and backup.get()):
            messagebox.showinfo("BackupProof", "Choose the original folder and its backup first.")
            return
        stop.clear()
        headline.configure(text=f"Checking ({mode})…", fg="black")
        tree.delete(*tree.get_children())

        def work():
            try:
                result = verify(source.get(), backup.get(), mode=mode, should_stop=stop.is_set,
                                progress=lambda d, t, p: messages.put(("progress", f"Reading files {d}/{t}: {p}")))
                messages.put(("done", result))
            except Exception as exc:
                messages.put(("error", str(exc)))

        threading.Thread(target=work, daemon=True).start()

    for label, mode in (("Quick check", "quick"), ("Sample check", "sample"), ("Deep check", "deep")):
        ttk.Button(buttons, text=label, command=lambda m=mode: start(m)).pack(side="left", padx=(0, 8))
    ttk.Button(buttons, text="Stop", command=stop.set).pack(side="left")

    def open_report() -> None:
        if state["result"] is not None and sys.platform == "win32":
            path = report.write_html(state["result"], Path(tempfile.gettempdir()) / "backupproof-report.html")
            os.startfile(path)  # noqa: S606 - local report in the default browser

    ttk.Button(buttons, text="Open full report", command=open_report).pack(side="left", padx=16)

    def pump() -> None:
        while True:
            try:
                kind, payload = messages.get_nowait()
            except queue.Empty:
                break
            if kind == "progress":
                status.configure(text=payload[:150])
            elif kind == "done":
                state["result"] = payload
                report.record(payload)
                headline.configure(text=payload.headline(), fg="#1f7a3a" if payload.ok else "#b91c1c")
                for row in report.rows(payload)[:2000]:
                    tree.insert("", "end", values=row)
                status.configure(text=f"{payload.files_checked:,} files checked in {payload.seconds}s. "
                                      f"Links/junctions skipped: {payload.links_skipped}.")
            elif kind == "error":
                headline.configure(text=f"Couldn't check: {payload}", fg="#b91c1c")
        root.after(150, pump)

    root.after(150, pump)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
