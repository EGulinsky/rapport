"""Linux FilesProvider — uses zenity or kdialog for native dialogs."""
from __future__ import annotations

import os
import subprocess

from agent.providers.base import FilesProvider


def _has_command(cmd: str) -> bool:
    try:
        subprocess.run(["which", cmd], capture_output=True, timeout=5)
        return True
    except (subprocess.SubprocessError, FileNotFoundError):
        return False


class LinuxFilesProvider(FilesProvider):
    def pick_folder(self, prompt: str) -> str | None:
        if _has_command("zenity"):
            result = subprocess.run(
                ["zenity", "--file-selection", "--directory", f"--title={prompt}"],
                capture_output=True, text=True, timeout=60,
            )
            return result.stdout.strip() or None
        elif _has_command("kdialog"):
            result = subprocess.run(
                ["kdialog", "--getexistingdirectory", "--title", prompt],
                capture_output=True, text=True, timeout=60,
            )
            return result.stdout.strip() or None
        else:
            try:
                import tkinter as tk
                from tkinter import filedialog

                root = tk.Tk()
                root.withdraw()
                path = filedialog.askdirectory(title=prompt)
                root.destroy()
                return path or None
            except ImportError:
                return None

    def pick_file(self, prompt: str, extensions: list[str]) -> str | None:
        filter_parts = []
        for ext in extensions:
            filter_parts.append(f"--file-filter={ext.upper()} files|*{ext}")

        if _has_command("zenity"):
            cmd = ["zenity", "--file-selection", f"--title={prompt}"] + filter_parts
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            return result.stdout.strip() or None
        elif _has_command("kdialog"):
            filter_str = " ".join(f"*{ext}" for ext in extensions)
            result = subprocess.run(
                ["kdialog", "--getopenfilename", "--title", prompt, ".", filter_str],
                capture_output=True, text=True, timeout=60,
            )
            return result.stdout.strip() or None
        else:
            try:
                import tkinter as tk
                from tkinter import filedialog

                filetypes = [(f"{ext.upper()} files", f"*{ext}") for ext in extensions]
                root = tk.Tk()
                root.withdraw()
                path = filedialog.askopenfilename(title=prompt, filetypes=filetypes)
                root.destroy()
                return path or None
            except ImportError:
                return None

    def open_path(self, path: str) -> None:
        subprocess.Popen(["xdg-open", path])
