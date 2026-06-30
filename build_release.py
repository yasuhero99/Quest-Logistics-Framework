"""
Build a Windows executable release for Quest Logistics Framework.

Output layout:

release/Quest-Logistics-Framework-v2.0-beta/
    QLF.exe          # GUI launcher users open
    bin/qlf_cli.exe  # CLI engine used internally by QLF.exe
    README.md
    LICENSE
    Projects/        # created automatically for GUI project workspaces

Run on Windows from the repository root:

    python build_release.py
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

APP_VERSION = "v2.0-beta"
RELEASE_NAME = f"Quest-Logistics-Framework-{APP_VERSION}"

ROOT = Path(__file__).resolve().parent
DIST = ROOT / "dist"
BUILD = ROOT / "build"
RELEASE_ROOT = ROOT / "release"
RELEASE_DIR = RELEASE_ROOT / RELEASE_NAME
BIN_DIR = RELEASE_DIR / "bin"


def run(cmd: list[str]) -> None:
    print("$", " ".join(cmd))
    subprocess.run(cmd, cwd=ROOT, check=True)


def ensure_pyinstaller() -> None:
    try:
        import PyInstaller  # noqa: F401
    except Exception:
        print("PyInstaller is not installed. Installing with pip...")
        run([sys.executable, "-m", "pip", "install", "pyinstaller"])


def clean() -> None:
    for path in [DIST, BUILD, RELEASE_DIR]:
        if path.exists():
            shutil.rmtree(path)
    for spec in ROOT.glob("*.spec"):
        spec.unlink()


def build() -> None:
    ensure_pyinstaller()
    clean()

    run([sys.executable, "-m", "PyInstaller", "--clean", "--onefile", "--name", "qlf_cli", "qlf.py"])
    run([sys.executable, "-m", "PyInstaller", "--clean", "--onefile", "--windowed", "--name", "QLF", "qlf_gui.py"])

    BIN_DIR.mkdir(parents=True, exist_ok=True)
    (RELEASE_DIR / "Projects").mkdir(parents=True, exist_ok=True)

    shutil.copy2(DIST / "QLF.exe", RELEASE_DIR / "QLF.exe")
    shutil.copy2(DIST / "qlf_cli.exe", BIN_DIR / "qlf_cli.exe")

    for name in ["README.md", "LICENSE"]:
        src = ROOT / name
        if src.exists():
            shutil.copy2(src, RELEASE_DIR / name)

    (RELEASE_DIR / "HOW_TO_RUN.txt").write_text(
        "Quest Logistics Framework\n"
        "=========================\n\n"
        "Open QLF.exe to start the graphical interface.\n\n"
        "Do not delete bin/qlf_cli.exe. QLF.exe uses it internally as the CLI engine.\n"
        "Projects will be stored in the Projects folder next to QLF.exe.\n",
        encoding="utf-8",
    )

    print("\nBuild complete:")
    print(RELEASE_DIR)
    print("\nUsers should open:")
    print(RELEASE_DIR / "QLF.exe")


if __name__ == "__main__":
    build()
