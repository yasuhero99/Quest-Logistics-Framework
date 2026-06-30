#!/usr/bin/env python3
"""
QLF GUI (v2.0-beta)

A simplified Project-based Tkinter front-end for Quest Logistics Framework.
The GUI intentionally calls the existing qlf.py CLI instead of reimplementing
core logic, so the command-line workflow remains the source of truth.

Design goals:
- Main Function page for normal users.
- Project workspace to prevent mixing files from different modpacks.
- State machine: buttons unlock only when the previous step is ready.
- Tools page for Diff / Adapter / SDK utilities.
"""

from __future__ import annotations

import json
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk


APP_TITLE = "Quest Logistics Framework - GUI v2.0-beta"
COMMON_LOCALES = [
    "en_us", "zh_tw", "zh_cn", "ja_jp", "ko_kr", "fr_fr", "de_de", "es_es", "ru_ru",
    "pt_br", "it_it", "pl_pl", "uk_ua",
]


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def sanitize_project_name(name: str) -> str:
    name = name.strip() or "QLF_Project"
    name = re.sub(r"[\\/:*?\"<>|]+", "_", name)
    name = re.sub(r"\s+", "_", name)
    name = re.sub(r"_+", "_", name).strip("_")
    return name or "QLF_Project"


def read_json(path: Path, default: dict | None = None) -> dict:
    if default is None:
        default = {}
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default
    return default


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def detect_minecraft_instance_roots() -> list[tuple[str, Path]]:
    """Return common Minecraft launcher instance/profile roots that exist on this machine."""
    home = Path.home()
    appdata = Path(os.environ.get("APPDATA", home / "AppData" / "Roaming"))
    localappdata = Path(os.environ.get("LOCALAPPDATA", home / "AppData" / "Local"))

    candidates: list[tuple[str, Path]] = [
        ("CurseForge", home / "curseforge" / "minecraft" / "Instances"),
        ("CurseForge", appdata / "CurseForge" / "minecraft" / "Instances"),
        ("Prism Launcher", appdata / "PrismLauncher" / "instances"),
        ("Prism Launcher", localappdata / "PrismLauncher" / "instances"),
        ("MultiMC", appdata / "MultiMC" / "instances"),
        ("Modrinth App", appdata / "com.modrinth.theseus" / "profiles"),
        ("Modrinth App", localappdata / "com.modrinth.theseus" / "profiles"),
        ("Official Minecraft", appdata / ".minecraft"),
    ]

    seen: set[str] = set()
    found: list[tuple[str, Path]] = []
    for label, path in candidates:
        try:
            resolved = str(path.resolve())
        except Exception:
            resolved = str(path)
        if resolved in seen:
            continue
        if path.exists() and path.is_dir():
            found.append((label, path))
            seen.add(resolved)
    return found


def best_minecraft_instance_root(settings: dict | None = None) -> tuple[str | None, Path | None]:
    """Choose the best initial folder for selecting a modpack instance."""
    settings = settings or {}
    last = settings.get("last_instance_root")
    if last:
        path = Path(last)
        if path.exists() and path.is_dir():
            return "Last Used", path

    roots = detect_minecraft_instance_roots()
    if roots:
        return roots[0]

    return None, None


class QLFGui(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1040x760")
        self.minsize(900, 640)
        self.resizable(True, True)

        if getattr(sys, "frozen", False):
            self.app_dir = Path(sys.executable).resolve().parent
        else:
            self.app_dir = Path(__file__).resolve().parent

        self.qlf_py = self.app_dir / "qlf.py"
        self.qlf_exe = self.app_dir / "bin" / "qlf_cli.exe"
        self.projects_root = self.app_dir / "Projects"
        self.settings_path = self.app_dir / "qlf_gui_settings.json"
        self.projects_root.mkdir(exist_ok=True)

        self.output_queue: queue.Queue[str | tuple[str, int, str | None]] = queue.Queue()
        self.running = False
        self.current_project: Path | None = None
        self.current_project_data: dict = {}

        self.project_var = tk.StringVar()
        self.instance_var = tk.StringVar()
        self.locale_var = tk.StringVar(value="en_us")
        self.translation_var = tk.StringVar()
        self.status_var = tk.StringVar(value="Ready")

        self.old_diff_var = tk.StringVar()
        self.new_diff_var = tk.StringVar()
        self.adapter_name_var = tk.StringVar(value="patchouli")
        self.adapter_out_var = tk.StringVar(value=str(self.app_dir / "qlf_core" / "adapters" / "patchouli.py"))

        self.project_names: list[str] = []

        self._build_ui()
        self._load_projects()
        self._load_last_project()
        self._update_state()
        self.after(100, self._drain_output_queue)

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        outer = ttk.Frame(self, padding=12)
        outer.pack(fill=tk.BOTH, expand=True)

        header = ttk.Frame(outer)
        header.pack(fill=tk.X)
        title = ttk.Label(header, text="Quest Logistics Framework", font=("Segoe UI", 18, "bold"))
        title.pack(side=tk.LEFT, anchor="w")
        self.status_badge = ttk.Label(header, textvariable=self.status_var, font=("Segoe UI", 10))
        self.status_badge.pack(side=tk.RIGHT, anchor="e")

        subtitle = ttk.Label(
            outer,
            text="Project-based workflow: Extract → Translate externally → Validate → Inject",
            font=("Segoe UI", 10),
        )
        subtitle.pack(anchor="w", pady=(0, 12))

        self.notebook = ttk.Notebook(outer)
        self.notebook.pack(fill=tk.BOTH, expand=True)

        self.main_tab = ttk.Frame(self.notebook, padding=10)
        self.projects_tab = ttk.Frame(self.notebook, padding=10)
        self.tools_tab = ttk.Frame(self.notebook, padding=10)
        self.logs_tab = ttk.Frame(self.notebook, padding=10)

        self.notebook.add(self.main_tab, text="Main Function")
        self.notebook.add(self.projects_tab, text="Projects")
        self.notebook.add(self.tools_tab, text="Tools")
        self.notebook.add(self.logs_tab, text="Logs")

        self._build_main_tab()
        self._build_projects_tab()
        self._build_tools_tab()
        self._build_logs_tab()

    def _build_main_tab(self) -> None:
        # Project selector
        project_box = ttk.LabelFrame(self.main_tab, text="1. Project", padding=10)
        project_box.pack(fill=tk.X, pady=(0, 8))

        project_row = ttk.Frame(project_box)
        project_row.pack(fill=tk.X)
        ttk.Label(project_row, text="Current Project", width=18).pack(side=tk.LEFT)
        self.project_combo = ttk.Combobox(project_row, textvariable=self.project_var, state="readonly")
        self.project_combo.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))
        self.project_combo.bind("<<ComboboxSelected>>", lambda _e: self._select_project_by_name(self.project_var.get()))
        ttk.Button(project_row, text="New Project", command=self.new_project).pack(side=tk.LEFT, padx=3)
        ttk.Button(project_row, text="Refresh", command=self.refresh_projects).pack(side=tk.LEFT, padx=3)

        instance_row = ttk.Frame(project_box)
        instance_row.pack(fill=tk.X, pady=(8, 0))
        ttk.Label(instance_row, text="Minecraft Instance", width=18).pack(side=tk.LEFT)
        self.instance_entry = ttk.Entry(instance_row, textvariable=self.instance_var)
        self.instance_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))
        ttk.Button(instance_row, text="Browse", command=self.browse_instance_for_project).pack(side=tk.LEFT)

        # Extract
        extract_box = ttk.LabelFrame(self.main_tab, text="2. Extract Quest Text", padding=10)
        extract_box.pack(fill=tk.X, pady=8)
        lang_row = ttk.Frame(extract_box)
        lang_row.pack(fill=tk.X)
        ttk.Label(lang_row, text="Export Language", width=18).pack(side=tk.LEFT)
        self.locale_combo = ttk.Combobox(lang_row, textvariable=self.locale_var, values=COMMON_LOCALES, width=18)
        self.locale_combo.pack(side=tk.LEFT, padx=(0, 8))
        self.extract_hint = ttk.Label(lang_row, text="Output will be saved under this Project folder.")
        self.extract_hint.pack(side=tk.LEFT)

        action_row = ttk.Frame(extract_box)
        action_row.pack(fill=tk.X, pady=(8, 0))
        self.extract_btn = ttk.Button(action_row, text="📤 Extract", command=self.extract_project)
        self.extract_btn.pack(side=tk.LEFT, padx=(0, 6))
        self.open_project_btn = ttk.Button(action_row, text="📂 Open Project Folder", command=self.open_project_folder)
        self.open_project_btn.pack(side=tk.LEFT, padx=6)
        self.open_source_btn = ttk.Button(action_row, text="Open Source Folder", command=lambda: self.open_subfolder("source"))
        self.open_source_btn.pack(side=tk.LEFT, padx=6)
        self.open_translated_btn = ttk.Button(action_row, text="Open Translated Folder", command=lambda: self.open_subfolder("translated"))
        self.open_translated_btn.pack(side=tk.LEFT, padx=6)

        # Translation detection / validation
        validate_box = ttk.LabelFrame(self.main_tab, text="3. Validate Translation", padding=10)
        validate_box.pack(fill=tk.X, pady=8)
        translation_row = ttk.Frame(validate_box)
        translation_row.pack(fill=tk.X)
        ttk.Label(translation_row, text="Detected JSON", width=18).pack(side=tk.LEFT)
        self.translation_combo = ttk.Combobox(translation_row, textvariable=self.translation_var, state="readonly")
        self.translation_combo.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))
        self.translation_combo.bind("<<ComboboxSelected>>", lambda _e: self._update_state())
        ttk.Button(translation_row, text="Scan", command=self.scan_translations).pack(side=tk.LEFT)

        validate_action = ttk.Frame(validate_box)
        validate_action.pack(fill=tk.X, pady=(8, 0))
        self.validate_btn = ttk.Button(validate_action, text="✔ Validate", command=self.validate_project)
        self.validate_btn.pack(side=tk.LEFT, padx=(0, 6))
        self.translation_hint = ttk.Label(
            validate_action,
            text="Put translated JSON files into translated/ then click Scan.",
        )
        self.translation_hint.pack(side=tk.LEFT)

        # Inject
        inject_box = ttk.LabelFrame(self.main_tab, text="4. Inject / Package", padding=10)
        inject_box.pack(fill=tk.X, pady=8)
        inject_row = ttk.Frame(inject_box)
        inject_row.pack(fill=tk.X)
        self.inject_btn = ttk.Button(inject_row, text="📥 Direct Inject", command=self.inject_project_direct)
        self.inject_btn.pack(side=tk.LEFT, padx=(0, 6))
        self.package_btn = ttk.Button(inject_row, text="📦 Build Package", command=self.inject_project_package)
        self.package_btn.pack(side=tk.LEFT, padx=6)
        self.open_package_btn = ttk.Button(inject_row, text="Open Package Folder", command=lambda: self.open_subfolder("package"))
        self.open_package_btn.pack(side=tk.LEFT, padx=6)

        # Progress
        progress_box = ttk.LabelFrame(self.main_tab, text="Progress", padding=10)
        progress_box.pack(fill=tk.BOTH, expand=True, pady=8)
        self.progress_labels: dict[str, ttk.Label] = {}
        for key, text in [
            ("project", "Project Created"),
            ("extract", "Extract Completed"),
            ("translation", "Translation File Detected"),
            ("validate", "Validation Passed"),
            ("inject", "Ready / Injected"),
        ]:
            lbl = ttk.Label(progress_box, text=f"○ {text}", font=("Segoe UI", 10))
            lbl.pack(anchor="w", pady=2)
            self.progress_labels[key] = lbl

        self.next_step_label = ttk.Label(progress_box, text="Next Step: Create or open a Project.", wraplength=880)
        self.next_step_label.pack(anchor="w", pady=(10, 0))

    def _build_projects_tab(self) -> None:
        top = ttk.Frame(self.projects_tab)
        top.pack(fill=tk.BOTH, expand=True)

        left = ttk.Frame(top)
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=False)
        ttk.Label(left, text="Projects", font=("Segoe UI", 12, "bold")).pack(anchor="w")
        self.project_list = tk.Listbox(left, width=34, height=22)
        self.project_list.pack(fill=tk.BOTH, expand=True, pady=6)
        self.project_list.bind("<<ListboxSelect>>", self._on_project_list_select)

        btns = ttk.Frame(left)
        btns.pack(fill=tk.X)
        ttk.Button(btns, text="Open", command=self.open_selected_project_from_list).pack(side=tk.LEFT, padx=2)
        ttk.Button(btns, text="Open Folder", command=self.open_project_folder).pack(side=tk.LEFT, padx=2)
        ttk.Button(btns, text="Delete", command=self.delete_selected_project).pack(side=tk.LEFT, padx=2)

        right = ttk.Frame(top, padding=(16, 0, 0, 0))
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        ttk.Label(right, text="Project Info", font=("Segoe UI", 12, "bold")).pack(anchor="w")
        self.project_info = tk.Text(right, height=24, wrap=tk.WORD)
        self.project_info.pack(fill=tk.BOTH, expand=True, pady=6)

    def _build_tools_tab(self) -> None:
        adapter_frame = ttk.LabelFrame(self.tools_tab, text="Adapters", padding=8)
        adapter_frame.pack(fill=tk.X, pady=6)
        ttk.Button(adapter_frame, text="List Adapters", command=self.list_adapters).pack(side=tk.LEFT, padx=4)
        ttk.Button(adapter_frame, text="FTBQuests Adapter Info", command=self.adapter_info_ftbquests).pack(side=tk.LEFT, padx=4)
        ttk.Button(adapter_frame, text="Detect Sources for Current Project", command=self.detect_sources).pack(side=tk.LEFT, padx=4)

        diff_frame = ttk.LabelFrame(self.tools_tab, text="Diff", padding=8)
        diff_frame.pack(fill=tk.X, pady=10)
        self._row(diff_frame, "Old File", self.old_diff_var, "file")
        self._row(diff_frame, "New File", self.new_diff_var, "file")
        ttk.Button(diff_frame, text="Run Diff", command=self.run_diff).pack(anchor="w", pady=4)

        template_frame = ttk.LabelFrame(self.tools_tab, text="Adapter Template", padding=8)
        template_frame.pack(fill=tk.X, pady=10)
        self._row(template_frame, "Adapter Name", self.adapter_name_var, None)
        self._row(template_frame, "Output File", self.adapter_out_var, "save")
        ttk.Button(template_frame, text="Generate Adapter Template", command=self.adapter_template).pack(anchor="w", pady=4)

    def _build_logs_tab(self) -> None:
        toolbar = ttk.Frame(self.logs_tab)
        toolbar.pack(fill=tk.X, pady=(0, 6))
        ttk.Button(toolbar, text="Clear Log", command=self.clear_log).pack(side=tk.LEFT)

        self.log = tk.Text(self.logs_tab, wrap=tk.WORD, height=28)
        self.log.pack(fill=tk.BOTH, expand=True, side=tk.LEFT)
        scrollbar = ttk.Scrollbar(self.logs_tab, command=self.log.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.log.configure(yscrollcommand=scrollbar.set)

    def _row(self, parent: ttk.Frame, label: str, variable: tk.StringVar, browse: str | None = None) -> ttk.Frame:
        row = ttk.Frame(parent)
        row.pack(fill=tk.X, pady=4)
        ttk.Label(row, text=label, width=14).pack(side=tk.LEFT)
        ttk.Entry(row, textvariable=variable).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))
        if browse == "dir":
            ttk.Button(row, text="Browse", command=lambda: self._browse_dir(variable)).pack(side=tk.LEFT)
        elif browse == "file":
            ttk.Button(row, text="Browse", command=lambda: self._browse_file(variable)).pack(side=tk.LEFT)
        elif browse == "save":
            ttk.Button(row, text="Save As", command=lambda: self._browse_save(variable)).pack(side=tk.LEFT)
        return row

    # ------------------------------------------------------------------
    # Project Management
    # ------------------------------------------------------------------

    def project_config_path(self, project_dir: Path | None = None) -> Path:
        base = project_dir or self.current_project
        if base is None:
            return self.projects_root / "__missing__" / "project.json"
        return base / "project.json"

    def _project_dirs(self) -> list[Path]:
        if not self.projects_root.exists():
            return []
        return sorted([p for p in self.projects_root.iterdir() if p.is_dir() and (p / "project.json").exists()])

    def _load_projects(self) -> None:
        self.project_names = [p.name for p in self._project_dirs()]
        self.project_combo["values"] = self.project_names
        self.project_list.delete(0, tk.END)
        for name in self.project_names:
            self.project_list.insert(tk.END, name)

    def _load_last_project(self) -> None:
        settings = read_json(self.settings_path)
        last = settings.get("last_project")
        if last and (self.projects_root / last / "project.json").exists():
            self._select_project_by_name(last)
        elif self.project_names:
            self._select_project_by_name(self.project_names[0])

    def _save_last_project(self) -> None:
        if self.current_project:
            settings = read_json(self.settings_path)
            settings["last_project"] = self.current_project.name
            settings["updated_at"] = now_iso()
            write_json(self.settings_path, settings)

    def _save_last_instance_root(self, instance_path: Path) -> None:
        settings = read_json(self.settings_path)
        settings["last_instance_root"] = str(instance_path.parent)
        settings["updated_at"] = now_iso()
        write_json(self.settings_path, settings)

    def _ask_modpack_instance_folder(self) -> Path | None:
        settings = read_json(self.settings_path)
        label, initial = best_minecraft_instance_root(settings)
        options = {"title": "Select Minecraft Modpack Instance Folder"}
        if initial is not None:
            options["initialdir"] = str(initial)
            self._log(f"[INFO] Opening instance selector at {label}: {initial}\n")
        else:
            self._log("[WARNING] No known Minecraft launcher folder detected. Please select the modpack instance manually.\n")

        selected = filedialog.askdirectory(**options)
        if not selected:
            return None
        instance_path = Path(selected)
        self._save_last_instance_root(instance_path)
        return instance_path

    def refresh_projects(self) -> None:
        current = self.current_project.name if self.current_project else None
        self._load_projects()
        if current and current in self.project_names:
            self._select_project_by_name(current)
        elif self.project_names:
            self._select_project_by_name(self.project_names[0])
        else:
            self.current_project = None
            self.current_project_data = {}
            self.project_var.set("")
            self._update_state()

    def new_project(self) -> None:
        instance_path = self._ask_modpack_instance_folder()
        if not instance_path:
            return
        default_name = sanitize_project_name(instance_path.name)
        name = simpledialog.askstring("New Project", "Project name:", initialvalue=default_name, parent=self)
        if not name:
            return
        project_name = sanitize_project_name(name)
        project_dir = self.projects_root / project_name

        if project_dir.exists():
            use_existing = messagebox.askyesno(
                "Project Exists",
                f"Project '{project_name}' already exists.\n\nOpen this existing project?",
            )
            if not use_existing:
                return
        else:
            self._create_project_structure(project_dir)
            data = {
                "name": project_name,
                "display_name": name.strip(),
                "instance_path": str(instance_path),
                "adapter": "ftbquests",
                "source_locale": self.locale_var.get() or "en_us",
                "created_at": now_iso(),
                "last_opened": now_iso(),
                "last_extract": None,
                "last_validate": None,
                "last_inject": None,
                "last_translation": None,
                "qlf_gui_version": "v2.0-beta",
            }
            write_json(project_dir / "project.json", data)

        self._load_projects()
        self._select_project_by_name(project_name)
        self._log(f"[INFO] Project ready: {project_name}\n")

    def _create_project_structure(self, project_dir: Path) -> None:
        for sub in ["source", "translated", "reports", "backups", "package"]:
            (project_dir / sub).mkdir(parents=True, exist_ok=True)
        (project_dir / "translated" / "README.txt").write_text(
            "Put translated JSON files here.\nExample: zh_tw.json, ja_jp.json, ko_kr.json\n",
            encoding="utf-8",
        )

    def _select_project_by_name(self, name: str) -> None:
        if not name:
            return
        project_dir = self.projects_root / name
        if not (project_dir / "project.json").exists():
            return
        self.current_project = project_dir
        self.current_project_data = read_json(project_dir / "project.json")
        self.current_project_data["last_opened"] = now_iso()
        write_json(project_dir / "project.json", self.current_project_data)
        self.project_var.set(name)
        self.instance_var.set(self.current_project_data.get("instance_path", ""))
        self.locale_var.set(self.current_project_data.get("source_locale", "en_us"))
        self._save_last_project()
        self.scan_translations(show_message=False)
        self._update_project_info()
        self._update_state()

    def browse_instance_for_project(self) -> None:
        instance_path = self._ask_modpack_instance_folder()
        if not instance_path:
            return
        path = str(instance_path)
        self.instance_var.set(path)
        if self.current_project:
            self.current_project_data["instance_path"] = path
            write_json(self.project_config_path(), self.current_project_data)
            self._update_project_info()
            self._update_state()

    def open_project_folder(self) -> None:
        if not self.current_project:
            messagebox.showinfo("No Project", "Please create or select a project first.")
            return
        self._open_path(self.current_project)

    def open_subfolder(self, subfolder: str) -> None:
        if not self.current_project:
            messagebox.showinfo("No Project", "Please create or select a project first.")
            return
        path = self.current_project / subfolder
        path.mkdir(parents=True, exist_ok=True)
        self._open_path(path)

    def _open_path(self, path: Path) -> None:
        try:
            if sys.platform.startswith("win"):
                os.startfile(str(path))  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(path)])
            else:
                subprocess.Popen(["xdg-open", str(path)])
        except Exception as exc:
            messagebox.showerror("Open Failed", str(exc))

    def _on_project_list_select(self, _event=None) -> None:
        idxs = self.project_list.curselection()
        if not idxs:
            return
        name = self.project_list.get(idxs[0])
        self._show_project_info(name)

    def _show_project_info(self, name: str) -> None:
        data = read_json(self.projects_root / name / "project.json")
        text = json.dumps(data, ensure_ascii=False, indent=2)
        self.project_info.delete("1.0", tk.END)
        self.project_info.insert(tk.END, text)

    def _update_project_info(self) -> None:
        if not self.current_project:
            self.project_info.delete("1.0", tk.END)
            return
        self._show_project_info(self.current_project.name)
        try:
            idx = self.project_names.index(self.current_project.name)
            self.project_list.selection_clear(0, tk.END)
            self.project_list.selection_set(idx)
            self.project_list.see(idx)
        except ValueError:
            pass

    def open_selected_project_from_list(self) -> None:
        idxs = self.project_list.curselection()
        if not idxs:
            return
        self._select_project_by_name(self.project_list.get(idxs[0]))
        self.notebook.select(self.main_tab)

    def delete_selected_project(self) -> None:
        idxs = self.project_list.curselection()
        if not idxs:
            return
        name = self.project_list.get(idxs[0])
        if not messagebox.askyesno("Delete Project", f"Delete project '{name}'?\n\nThis deletes the QLF workspace only, not your Minecraft instance."):
            return
        shutil.rmtree(self.projects_root / name, ignore_errors=True)
        self.refresh_projects()

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------

    def source_file(self) -> Path | None:
        if not self.current_project:
            return None
        locale = self.locale_var.get().strip() or "en_us"
        return self.current_project / "source" / f"{locale}.json"

    def manifest_file(self) -> Path | None:
        if not self.current_project:
            return None
        return self.current_project / "manifest.json"

    def selected_translation_file(self) -> Path | None:
        if not self.current_project:
            return None
        value = self.translation_var.get().strip()
        if not value:
            return None
        path = Path(value)
        if not path.is_absolute():
            path = self.current_project / "translated" / value
        return path

    def scan_translations(self, show_message: bool = True) -> None:
        if not self.current_project:
            self.translation_combo["values"] = []
            self.translation_var.set("")
            self._update_state()
            return
        folder = self.current_project / "translated"
        folder.mkdir(parents=True, exist_ok=True)
        files = sorted([p.name for p in folder.glob("*.json")])
        self.translation_combo["values"] = files
        current = self.translation_var.get()
        if current not in files:
            self.translation_var.set(files[0] if files else "")
        if show_message:
            if files:
                self._log(f"[INFO] Detected translated JSON: {', '.join(files)}\n")
            else:
                self._log(f"[INFO] No translated JSON found in: {folder}\n")
        self._update_state()

    def _update_state(self) -> None:
        has_project = self.current_project is not None
        instance = self.instance_var.get().strip()
        manifest = self.manifest_file()
        source = self.source_file()
        translation = self.selected_translation_file()
        has_manifest = bool(manifest and manifest.exists())
        has_source = bool(source and source.exists())
        has_translation = bool(translation and translation.exists())
        validated = bool(
            self.current_project_data.get("last_validate")
            and self.current_project_data.get("last_translation") == (translation.name if translation else None)
        )

        self.extract_btn.configure(state=tk.NORMAL if has_project and instance and not self.running else tk.DISABLED)
        self.open_project_btn.configure(state=tk.NORMAL if has_project else tk.DISABLED)
        self.open_source_btn.configure(state=tk.NORMAL if has_project else tk.DISABLED)
        self.open_translated_btn.configure(state=tk.NORMAL if has_project else tk.DISABLED)
        self.validate_btn.configure(state=tk.NORMAL if has_project and has_manifest and has_translation and not self.running else tk.DISABLED)
        self.inject_btn.configure(state=tk.NORMAL if has_project and validated and not self.running else tk.DISABLED)
        self.package_btn.configure(state=tk.NORMAL if has_project and validated and not self.running else tk.DISABLED)
        self.open_package_btn.configure(state=tk.NORMAL if has_project else tk.DISABLED)

        self.progress_labels["project"].configure(text=("✓" if has_project else "○") + " Project Created")
        self.progress_labels["extract"].configure(text=("✓" if has_manifest and has_source else "○") + " Extract Completed")
        self.progress_labels["translation"].configure(text=("✓" if has_translation else "○") + " Translation File Detected")
        self.progress_labels["validate"].configure(text=("✓" if validated else "○") + " Validation Passed")
        self.progress_labels["inject"].configure(text=("✓" if self.current_project_data.get("last_inject") else "○") + " Ready / Injected")

        if not has_project:
            next_step = "Next Step: Create a Project."
        elif not instance:
            next_step = "Next Step: Select the Minecraft modpack instance folder."
        elif not (has_manifest and has_source):
            next_step = "Next Step: Click Extract. QLF will create source JSON and manifest in this Project."
        elif not has_translation:
            next_step = "Next Step: Open Project Folder, translate the JSON, then put the translated file into translated/."
        elif not validated:
            next_step = "Next Step: Click Validate."
        else:
            next_step = "Next Step: Click Direct Inject or Build Package."
        self.next_step_label.configure(text=next_step)
        self.status_var.set("Running..." if self.running else next_step.replace("Next Step: ", ""))

    # ------------------------------------------------------------------
    # Browsing helpers
    # ------------------------------------------------------------------

    def _browse_dir(self, variable: tk.StringVar) -> None:
        path = filedialog.askdirectory()
        if path:
            variable.set(path)

    def _browse_file(self, variable: tk.StringVar) -> None:
        path = filedialog.askopenfilename(filetypes=[("JSON/SNBT files", "*.json *.snbt"), ("All files", "*.*")])
        if path:
            variable.set(path)

    def _browse_save(self, variable: tk.StringVar) -> None:
        path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON files", "*.json"), ("Python files", "*.py"), ("All files", "*.*")])
        if path:
            variable.set(path)

    # ------------------------------------------------------------------
    # CLI runner
    # ------------------------------------------------------------------

    def _python_cmd(self) -> str:
        return sys.executable or "python"

    def _quote(self, s: str) -> str:
        if " " in s or "\\" in s or "/" in s:
            return f'"{s}"'
        return s

    def _run(self, args: list[str], title: str, on_success: str | None = None) -> None:
        if self.running:
            messagebox.showinfo("Running", "QLF is already running a command.")
            return

        if getattr(sys, "frozen", False):
            if not self.qlf_exe.exists():
                messagebox.showerror(
                    "Missing qlf.exe",
                    f"Cannot find qlf_cli.exe at:\n{self.qlf_exe}\n\n"
                    "The executable release must keep QLF.exe and bin/qlf_cli.exe together."
                )
                return
            cmd = [str(self.qlf_exe), *args]
        else:
            if not self.qlf_py.exists():
                messagebox.showerror("Missing qlf.py", f"Cannot find qlf.py at:\n{self.qlf_py}")
                return
            cmd = [self._python_cmd(), str(self.qlf_py), *args]

        self.running = True
        self._update_state()
        self._log(f"\n=== {title} ===\n")
        self._log("$ " + " ".join(self._quote(c) for c in cmd) + "\n")
        thread = threading.Thread(target=self._run_worker, args=(cmd, on_success), daemon=True)
        thread.start()

    def _run_worker(self, cmd: list[str], on_success: str | None) -> None:
        try:
            proc = subprocess.run(
                cmd,
                cwd=str(self.app_dir),
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
            self.output_queue.put(("__DONE__", proc.returncode, on_success))
        except Exception as exc:
            self.output_queue.put(f"\n[error] {exc}\n")
            self.output_queue.put(("__DONE__", 1, None))

    def _drain_output_queue(self) -> None:
        try:
            while True:
                item = self.output_queue.get_nowait()
                if isinstance(item, tuple) and item[0] == "__DONE__":
                    _tag, code, on_success = item
                    self.running = False
                    if code == 0 and on_success:
                        self._handle_success(on_success)
                    else:
                        if on_success == "validate":
                            self._handle_validate_failure()
                        else:
                            self._update_state()
                    continue
                assert isinstance(item, str)
                self._log(item)
        except queue.Empty:
            pass
        self.after(100, self._drain_output_queue)

    def _handle_validate_failure(self) -> None:
        """Show validation errors when the CLI exits with a non-zero code.

        The CLI is the source of truth. A non-zero validation exit means at least
        one blocking error exists, such as missing keys, duplicate keys, or type
        mismatches. Warnings alone should exit with 0 and are handled by
        _handle_success("validate").
        """
        if self.current_project:
            self.current_project_data["last_validate"] = None
            self.current_project_data["last_translation"] = None
            write_json(self.project_config_path(), self.current_project_data)

        translation = self.selected_translation_file()
        errors: list[str] = []
        warnings: list[str] = []
        report_path = None
        if self.current_project and translation:
            report_path = self.current_project / "reports" / f"validate_{translation.stem}.json"
            try:
                report = read_json(report_path, {})
                errors = report.get("errors", []) or []
                warnings = report.get("warnings", []) or []
            except Exception:
                errors = []
                warnings = []

        message = "Validation failed. Please fix blocking errors before Direct Inject or Package Mode."
        if errors:
            message += "\n\nErrors:\n" + "\n".join(f"• {e}" for e in errors[:8])
            if len(errors) > 8:
                message += f"\n• ... and {len(errors) - 8} more"
        if warnings:
            message += "\n\nWarnings:\n" + "\n".join(f"• {w}" for w in warnings[:8])
            if len(warnings) > 8:
                message += f"\n• ... and {len(warnings) - 8} more"
        if report_path:
            message += f"\n\nReport:\n{report_path}"

        messagebox.showerror("Validation Failed", message)
        self._update_project_info()
        self._update_state()

    def _handle_success(self, action: str) -> None:
        if not self.current_project:
            self._update_state()
            return
        if action == "extract":
            self.current_project_data["source_locale"] = self.locale_var.get().strip() or "en_us"
            self.current_project_data["last_extract"] = now_iso()
            self.current_project_data["last_validate"] = None
            self.current_project_data["last_inject"] = None
            self.current_project_data["last_translation"] = None
            write_json(self.project_config_path(), self.current_project_data)
            self.scan_translations(show_message=False)
            messagebox.showinfo(
                "Extract Completed",
                f"Extract completed.\n\nSource file:\n{self.source_file()}\n\nNext step:\nOpen Project Folder, translate the JSON, then put the translated file into translated/.",
            )
        elif action == "validate":
            translation = self.selected_translation_file()
            self.current_project_data["last_validate"] = now_iso()
            self.current_project_data["last_translation"] = translation.name if translation else None
            write_json(self.project_config_path(), self.current_project_data)
            warning_text = ""
            if translation:
                report_path = self.current_project / "reports" / f"validate_{translation.stem}.json"
                try:
                    report = read_json(report_path, {})
                    warnings = report.get("warnings", []) or []
                    if warnings:
                        warning_text = "\n\nWarnings:\n" + "\n".join(f"• {w}" for w in warnings[:8])
                        if len(warnings) > 8:
                            warning_text += f"\n• ... and {len(warnings) - 8} more"
                except Exception:
                    warning_text = ""
            messagebox.showinfo(
                "Validation Passed",
                "Validation completed successfully."
                + warning_text
                + "\n\nWarnings do not block Direct Inject or Package Mode.",
            )
        elif action == "inject":
            self.current_project_data["last_inject"] = now_iso()
            write_json(self.project_config_path(), self.current_project_data)
            messagebox.showinfo("Inject Completed", "Inject completed successfully.")
        elif action == "package":
            self.current_project_data["last_package"] = now_iso()
            write_json(self.project_config_path(), self.current_project_data)
            messagebox.showinfo("Package Completed", f"Package completed.\n\nFolder:\n{self.current_project / 'package'}")
        self._update_project_info()
        self._update_state()

    def _log(self, text: str) -> None:
        self.log.insert(tk.END, text)
        self.log.see(tk.END)

    def clear_log(self) -> None:
        self.log.delete("1.0", tk.END)

    # ------------------------------------------------------------------
    # Main workflow actions
    # ------------------------------------------------------------------

    def detect_sources(self) -> None:
        instance = self.instance_var.get().strip()
        if not instance:
            messagebox.showerror("Missing Instance", "Please select a Minecraft modpack instance folder.")
            return
        self._run(["sources", "--instance", instance], "Detect Sources")

    def extract_project(self) -> None:
        if not self.current_project:
            messagebox.showerror("No Project", "Please create or select a Project first.")
            return
        instance = self.instance_var.get().strip()
        if not instance:
            messagebox.showerror("Missing Instance", "Please select a Minecraft modpack instance folder.")
            return
        locale = self.locale_var.get().strip() or "en_us"
        self.current_project_data["instance_path"] = instance
        self.current_project_data["source_locale"] = locale
        write_json(self.project_config_path(), self.current_project_data)
        out = self.current_project / "source" / f"{locale}.json"
        manifest = self.current_project / "manifest.json"
        report = self.current_project / "reports" / "resolve_report.json"
        self._run(
            [
                "resolve-text",
                instance,
                "--out", str(out),
                "--manifest", str(manifest),
                "--report", str(report),
            ],
            "Extract",
            on_success="extract",
        )

    def validate_project(self) -> None:
        if not self.current_project:
            return
        manifest = self.manifest_file()
        translation = self.selected_translation_file()
        if not manifest or not manifest.exists():
            messagebox.showerror("Missing Manifest", "Please run Extract first.")
            return
        if not translation or not translation.exists():
            messagebox.showerror(
                "No Translation Found",
                f"Please put translated JSON files into:\n{self.current_project / 'translated'}",
            )
            return
        report = self.current_project / "reports" / f"validate_{translation.stem}.json"
        self._run(
            [
                "validate",
                "--manifest", str(manifest),
                "--target", str(translation),
                "--report", str(report),
            ],
            "Validate",
            on_success="validate",
        )

    def inject_project_direct(self) -> None:
        if not self.current_project:
            return
        instance = self.current_project_data.get("instance_path") or self.instance_var.get().strip()
        manifest = self.manifest_file()
        translation = self.selected_translation_file()
        if not instance or not manifest or not translation:
            return
        locale = translation.stem
        report = self.current_project / "reports" / f"inject_{locale}.json"
        self._run(
            [
                "inject",
                "--translation", str(translation),
                "--manifest", str(manifest),
                "--locale", locale,
                "--write-to-instance", str(instance),
                "--report", str(report),
            ],
            "Direct Inject",
            on_success="inject",
        )

    def inject_project_package(self) -> None:
        if not self.current_project:
            return
        manifest = self.manifest_file()
        translation = self.selected_translation_file()
        if not manifest or not translation:
            return
        locale = translation.stem
        out_dir = self.current_project / "package" / locale
        report = self.current_project / "reports" / f"package_{locale}.json"
        self._run(
            [
                "inject",
                "--translation", str(translation),
                "--manifest", str(manifest),
                "--locale", locale,
                "--out-dir", str(out_dir),
                "--report", str(report),
            ],
            "Build Package",
            on_success="package",
        )

    # ------------------------------------------------------------------
    # Tools
    # ------------------------------------------------------------------

    def list_adapters(self) -> None:
        self._run(["adapters"], "List Adapters")

    def adapter_info_ftbquests(self) -> None:
        self._run(["adapter-info", "ftbquests"], "Adapter Info: ftbquests")

    def run_diff(self) -> None:
        old = self.old_diff_var.get().strip()
        new = self.new_diff_var.get().strip()
        if not old or not new:
            messagebox.showerror("Missing File", "Please select both old and new files.")
            return
        report = self.app_dir / "diff_report.json"
        self._run(["diff", "--old", old, "--new", new, "--report", str(report)], "Diff")

    def adapter_template(self) -> None:
        name = self.adapter_name_var.get().strip()
        out = self.adapter_out_var.get().strip()
        if not name:
            messagebox.showerror("Missing Adapter Name", "Please enter an adapter name.")
            return
        self._run(["adapter-template", name, "--out", out], "Generate Adapter Template")


if __name__ == "__main__":
    app = QLFGui()
    app.mainloop()
