"""Windows FilesProvider — uses tkinter for native dialogs."""
from __future__ import annotations

import os
import subprocess
import sys

from agent.providers.base import FilesProvider


class WindowsFilesProvider(FilesProvider):
    def pick_folder(self, prompt: str) -> str | None:
        try:
            import tkinter as tk
            from tkinter import filedialog

            root = tk.Tk()
            root.withdraw()
            root.wm_attributes("-topmost", True)
            path = filedialog.askdirectory(title=prompt)
            root.destroy()
            return path or None
        except ImportError:
            return None

    def pick_file(self, prompt: str, extensions: list[str]) -> str | None:
        try:
            import tkinter as tk
            from tkinter import filedialog

            filetypes = [(f"{ext.upper()} files", f"*{ext}") for ext in extensions]
            root = tk.Tk()
            root.withdraw()
            root.wm_attributes("-topmost", True)
            path = filedialog.askopenfilename(title=prompt, filetypes=filetypes)
            root.destroy()
            return path or None
        except ImportError:
            return None

    def open_path(self, path: str) -> None:
        if sys.platform == "win32":
            os.startfile(path)
        else:
            subprocess.Popen(["xdg-open", path])
