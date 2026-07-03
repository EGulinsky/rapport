"""macOS FilesProvider — ported 1:1 from files_bridge.py's osascript calls."""
from __future__ import annotations

import subprocess

from agent.providers.base import FilesProvider


class MacFilesProvider(FilesProvider):
    def pick_folder(self, prompt: str) -> str | None:
        result = subprocess.run(
            ["osascript", "-e", f'POSIX path of (choose folder with prompt "{prompt}")'],
            capture_output=True, text=True, timeout=60,
        )
        path = result.stdout.strip().rstrip("/")
        return path or None

    def pick_file(self, prompt: str, extensions: list[str]) -> str | None:
        type_list = ", ".join(f'"{ext}"' for ext in extensions)
        script = f'POSIX path of (choose file with prompt "{prompt}" of type {{{type_list}}})'
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=60,
        )
        path = result.stdout.strip()
        return path or None

    def open_path(self, path: str) -> None:
        subprocess.Popen(["open", path])
