#!/usr/bin/env python3
"""
QLF GUI (v2.0-alpha)

A simple Tkinter front-end for Quest Logistics Framework.
This GUI intentionally calls the existing qlf.py CLI instead of reimplementing
core logic, so the command-line workflow remains the source of truth.
"""

from __future__ import annotations

import json
import queue
import subprocess
import sys
import threading
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk


APP_TITLE = "Quest Logistics Framework - GUI v2.0-alpha"


class QLFGui(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("980x720")
        self.minsize(860, 600)

        self.project_dir = Path(__file__).resolve().parent
        self.qlf_py = self.project_dir / "qlf.py"

        self.instance_var = tk.StringVar()
        self.source_json_var = tk.StringVar(value=str(self.project_dir / "en_us.json"))
        self.manifest_var = tk.StringVar(value=str(self.project_dir / "manifest.json"))
        self.target_json_var = tk.StringVar(value=str(self.project_dir / "zh_tw.json"))
        self.locale_var = tk.StringVar(value="zh_tw")
        self.package_out_var = tk.StringVar(value=str(self.project_dir / "qlf_package"))
        self.old_diff_var = tk.StringVar(value=str(self.project_dir / "en_us.json"))
        self.new_diff_var = tk.StringVar(value=str(self.project_dir / "zh_tw.json"))

        self.output_queue: queue.Queue[str] = queue.Queue()

        self._build_ui()
        self.after(100, self._drain_output_queue)

    # ---------- UI ----------

    def _build_ui(self) -> None:
        outer = ttk.Frame(self, padding=12)
        outer.pack(fill=tk.BOTH, expand=True)

        title = ttk.Label(outer, text="Quest Logistics Framework", font=("Segoe UI", 18, "bold"))
        title.pack(anchor="w")

        subtitle = ttk.Label(
            outer,
            text="Extract → Translate externally → Validate → Inject",
            font=("Segoe UI", 10),
        )
        subtitle.pack(anchor="w", pady=(0, 12))

        notebook = ttk.Notebook(outer)
        notebook.pack(fill=tk.BOTH, expand=True)

        self.workflow_tab = ttk.Frame(notebook, padding=10)
        self.tools_tab = ttk.Frame(notebook, padding=10)
        self.log_tab = ttk.Frame(notebook, padding=10)

        notebook.add(self.workflow_tab, text="Workflow")
        notebook.add(self.tools_tab, text="Tools")
        notebook.add(self.log_tab, text="Log")

        self._build_workflow_tab()
        self._build_tools_tab()
        self._build_log_tab()

    def _row(self, parent: ttk.Frame, label: str, variable: tk.StringVar, browse: str | None = None) -> ttk.Frame:
        row = ttk.Frame(parent)
        row.pack(fill=tk.X, pady=4)

        ttk.Label(row, text=label, width=18).pack(side=tk.LEFT)
        entry = ttk.Entry(row, textvariable=variable)
        entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))

        if browse == "dir":
            ttk.Button(row, text="Browse", command=lambda: self._browse_dir(variable)).pack(side=tk.LEFT)
        elif browse == "file":
            ttk.Button(row, text="Browse", command=lambda: self._browse_file(variable)).pack(side=tk.LEFT)
        elif browse == "save":
            ttk.Button(row, text="Save As", command=lambda: self._browse_save(variable)).pack(side=tk.LEFT)

        return row

    def _build_workflow_tab(self) -> None:
        info = ttk.Label(
            self.workflow_tab,
            text="Paste or browse your Minecraft modpack instance folder, then run the workflow.",
            wraplength=850,
        )
        info.pack(anchor="w", pady=(0, 8))

        self._row(self.workflow_tab, "Modpack Instance", self.instance_var, "dir")
        self._row(self.workflow_tab, "Source JSON", self.source_json_var, "save")
        self._row(self.workflow_tab, "Manifest", self.manifest_var, "save")
        self._row(self.workflow_tab, "Target JSON", self.target_json_var, "file")

        locale_row = ttk.Frame(self.workflow_tab)
        locale_row.pack(fill=tk.X, pady=4)
        ttk.Label(locale_row, text="Target Locale", width=18).pack(side=tk.LEFT)
        ttk.Entry(locale_row, textvariable=self.locale_var, width=18).pack(side=tk.LEFT)
        ttk.Label(locale_row, text="Examples: zh_tw, ja_jp, ko_kr, fr_fr, en_gb").pack(side=tk.LEFT, padx=8)

        ttk.Separator(self.workflow_tab).pack(fill=tk.X, pady=12)

        buttons = ttk.Frame(self.workflow_tab)
        buttons.pack(fill=tk.X)

        ttk.Button(buttons, text="1. Detect Sources", command=self.detect_sources).pack(side=tk.LEFT, padx=4, pady=4)
        ttk.Button(buttons, text="2. Extract", command=self.extract).pack(side=tk.LEFT, padx=4, pady=4)
        ttk.Button(buttons, text="3. Validate", command=self.validate).pack(side=tk.LEFT, padx=4, pady=4)
        ttk.Button(buttons, text="4. Inject Direct Write", command=self.inject_direct).pack(side=tk.LEFT, padx=4, pady=4)

        package = ttk.LabelFrame(self.workflow_tab, text="Package Mode", padding=8)
        package.pack(fill=tk.X, pady=12)
        self._row(package, "Package Output", self.package_out_var, "dir")
        ttk.Button(package, text="Inject Package Mode", command=self.inject_package).pack(anchor="w", pady=4)

        notes = ttk.Label(
            self.workflow_tab,
            text=(
                "Note: QLF does not translate text. After Extract, translate the Source JSON externally, "
                "save it as the Target JSON, then run Validate and Inject."
            ),
            wraplength=850,
        )
        notes.pack(anchor="w", pady=10)

    def _build_tools_tab(self) -> None:
        adapter_frame = ttk.LabelFrame(self.tools_tab, text="Adapters", padding=8)
        adapter_frame.pack(fill=tk.X, pady=6)

        ttk.Button(adapter_frame, text="List Adapters", command=self.list_adapters).pack(side=tk.LEFT, padx=4)
        ttk.Button(adapter_frame, text="FTBQuests Adapter Info", command=self.adapter_info_ftbquests).pack(side=tk.LEFT, padx=4)

        diff_frame = ttk.LabelFrame(self.tools_tab, text="Diff", padding=8)
        diff_frame.pack(fill=tk.X, pady=10)

        self._row(diff_frame, "Old File", self.old_diff_var, "file")
        self._row(diff_frame, "New File", self.new_diff_var, "file")
        ttk.Button(diff_frame, text="Run Diff", command=self.run_diff).pack(anchor="w", pady=4)

        template_frame = ttk.LabelFrame(self.tools_tab, text="Adapter Template", padding=8)
        template_frame.pack(fill=tk.X, pady=10)

        self.adapter_name_var = tk.StringVar(value="patchouli")
        self.adapter_out_var = tk.StringVar(value=str(self.project_dir / "qlf_core" / "adapters" / "patchouli.py"))

        self._row(template_frame, "Adapter Name", self.adapter_name_var, None)
        self._row(template_frame, "Output File", self.adapter_out_var, "save")
        ttk.Button(template_frame, text="Generate Adapter Template", command=self.adapter_template).pack(anchor="w", pady=4)

    def _build_log_tab(self) -> None:
        toolbar = ttk.Frame(self.log_tab)
        toolbar.pack(fill=tk.X, pady=(0, 6))
        ttk.Button(toolbar, text="Clear Log", command=self.clear_log).pack(side=tk.LEFT)

        self.log = tk.Text(self.log_tab, wrap=tk.WORD, height=28)
        self.log.pack(fill=tk.BOTH, expand=True)

        scrollbar = ttk.Scrollbar(self.log, command=self.log.yview)
        self.log.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    # ---------- Browsing ----------

    def _browse_dir(self, variable: tk.StringVar) -> None:
        path = filedialog.askdirectory()
        if path:
            variable.set(path)

    def _browse_file(self, variable: tk.StringVar) -> None:
        path = filedialog.askopenfilename(
            filetypes=[
                ("JSON/SNBT files", "*.json *.snbt"),
                ("All files", "*.*"),
            ]
        )
        if path:
            variable.set(path)

    def _browse_save(self, variable: tk.StringVar) -> None:
        path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[
                ("JSON files", "*.json"),
                ("Python files", "*.py"),
                ("All files", "*.*"),
            ],
        )
        if path:
            variable.set(path)

    # ---------- Commands ----------

    def _python_cmd(self) -> str:
        return sys.executable or "python"

    def _run(self, args: list[str], title: str) -> None:
        if not self.qlf_py.exists():
            messagebox.showerror("Missing qlf.py", f"Cannot find qlf.py at:\n{self.qlf_py}")
            return

        cmd = [self._python_cmd(), str(self.qlf_py), *args]
        self._log(f"\n=== {title} ===\n")
        self._log("$ " + " ".join(self._quote(c) for c in cmd) + "\n")

        thread = threading.Thread(target=self._run_worker, args=(cmd,), daemon=True)
        thread.start()

    def _run_worker(self, cmd: list[str]) -> None:
        try:
            proc = subprocess.run(
                cmd,
                cwd=str(self.project_dir),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            if proc.stdout:
                self.output_queue.put(proc.stdout)
            if proc.stderr:
                self.output_queue.put(proc.stderr)
            self.output_queue.put(f"\n[exit code: {proc.returncode}]\n")
        except Exception as exc:
            self.output_queue.put(f"\n[error] {exc}\n")

    def _quote(self, s: str) -> str:
        if " " in s or "\\" in s:
            return f'"{s}"'
        return s

    def detect_sources(self) -> None:
        instance = self.instance_var.get().strip()
        if not instance:
            messagebox.showerror("Missing path", "Please select or paste a modpack instance folder.")
            return
        self._run(["sources", "--instance", instance], "Detect Sources")

    def extract(self) -> None:
        instance = self.instance_var.get().strip()
        out = self.source_json_var.get().strip()
        manifest = self.manifest_var.get().strip()
        if not instance:
            messagebox.showerror("Missing path", "Please select or paste a modpack instance folder.")
            return
        self._run(
            [
                "resolve-text",
                instance,
                "--out", out,
                "--manifest", manifest,
                "--report", "resolve_report.json",
            ],
            "Extract",
        )

    def validate(self) -> None:
        manifest = self.manifest_var.get().strip()
        target = self.target_json_var.get().strip()
        self._run(
            [
                "validate",
                "--manifest", manifest,
                "--target", target,
                "--report", "validate_report.json",
            ],
            "Validate",
        )

    def inject_direct(self) -> None:
        instance = self.instance_var.get().strip()
        translation = self.target_json_var.get().strip()
        manifest = self.manifest_var.get().strip()
        locale = self.locale_var.get().strip() or "zh_tw"
        if not instance:
            messagebox.showerror("Missing path", "Please select or paste a modpack instance folder.")
            return
        self._run(
            [
                "inject",
                "--translation", translation,
                "--manifest", manifest,
                "--locale", locale,
                "--write-to-instance", instance,
                "--report", "inject_report.json",
            ],
            "Inject Direct Write",
        )

    def inject_package(self) -> None:
        translation = self.target_json_var.get().strip()
        manifest = self.manifest_var.get().strip()
        locale = self.locale_var.get().strip() or "zh_tw"
        out_dir = self.package_out_var.get().strip()
        self._run(
            [
                "inject",
                "--translation", translation,
                "--manifest", manifest,
                "--locale", locale,
                "--out-dir", out_dir,
                "--report", "inject_report.json",
            ],
            "Inject Package Mode",
        )

    def list_adapters(self) -> None:
        self._run(["adapters"], "List Adapters")

    def adapter_info_ftbquests(self) -> None:
        self._run(["adapter-info", "ftbquests"], "Adapter Info: ftbquests")

    def run_diff(self) -> None:
        old = self.old_diff_var.get().strip()
        new = self.new_diff_var.get().strip()
        self._run(
            [
                "diff",
                "--old", old,
                "--new", new,
                "--report", "diff_report.json",
            ],
            "Diff",
        )

    def adapter_template(self) -> None:
        name = self.adapter_name_var.get().strip()
        out = self.adapter_out_var.get().strip()
        if not name:
            messagebox.showerror("Missing adapter name", "Please enter an adapter name.")
            return
        self._run(
            [
                "adapter-template",
                name,
                "--out", out,
            ],
            "Generate Adapter Template",
        )

    # ---------- Log ----------

    def _log(self, text: str) -> None:
        self.log.insert(tk.END, text)
        self.log.see(tk.END)

    def _drain_output_queue(self) -> None:
        try:
            while True:
                self._log(self.output_queue.get_nowait())
        except queue.Empty:
            pass
        self.after(100, self._drain_output_queue)

    def clear_log(self) -> None:
        self.log.delete("1.0", tk.END)


if __name__ == "__main__":
    app = QLFGui()
    app.mainloop()
