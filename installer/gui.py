"""Graphical installer wizard for Windows -- replaces the bare console
window (installer/main.py's flow, still used as-is on macOS/Linux) with a
real installer experience: a title, a live status line, a progress bar, a
scrollback log, and buttons that make sense once the run finishes or
fails.

A console window that just prints text and might flash-close on error
looks broken even when the message it printed was perfectly clear -- this
keeps the window open and the error visible no matter what happens, with
a Retry button once Docker (or the network) is in a better state.

Runs the actual bootstrap work in a background thread (tkinter itself is
not thread-safe) and bridges progress back to the GUI thread via a
queue.Queue, drained on a `root.after()` timer -- the standard, supported
way to talk to tkinter from a worker thread. Reuses the exact same
collaborator functions main.py's console flow calls (docker_check,
docker_install, compose_writer, health, browser) rather than a shared
abstraction, since the two flows differ enough in shape (threaded status
callbacks vs. plain print()) that factoring them together would obscure
more than it'd save.
"""
from __future__ import annotations

import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import ttk

from installer.browser import open_app, APP_URL
from installer.compose_writer import write_compose_file
from installer.docker_check import docker_cli_available, docker_cmd_prefix, docker_daemon_running
from installer.docker_install import install_docker
from installer.health import wait_for_healthy

_POLL_MS = 80

# Windows only -- keeps a subprocess.run() call from this console-less (GUI)
# process spawning its own flashing console window for every docker/compose
# invocation.
_SUBPROCESS_KWARGS: dict = {}
if sys.platform == "win32":
    _SUBPROCESS_KWARGS["creationflags"] = subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]


class _QueueWriter:
    """A file-like object that pushes each written line onto the same
    queue used for status/done/error events, tagged "log" -- lets
    install_docker()'s existing print() calls show up in the GUI's log box
    without changing any of that code."""

    def __init__(self, q: "queue.Queue[tuple[str, str]]") -> None:
        self._queue = q
        self._buffer = ""

    def write(self, text: str) -> int:
        self._buffer += text
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            if line.strip():
                self._queue.put(("log", line))
        return len(text)

    def flush(self) -> None:
        pass


class InstallerWindow:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("Rapport Installer")
        self.root.geometry("560x440")
        self.root.minsize(560, 440)
        self._queue: "queue.Queue[tuple[str, str]]" = queue.Queue()
        self._build_widgets()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._start_worker()
        self.root.after(_POLL_MS, self._drain_queue)

    def _build_widgets(self) -> None:
        outer = tk.Frame(self.root, padx=24, pady=20)
        outer.pack(fill="both", expand=True)

        tk.Label(outer, text="Setting up rapport", font=("Segoe UI", 15, "bold")).pack(anchor="w")

        self.status_var = tk.StringVar(value="Starting…")
        tk.Label(
            outer, textvariable=self.status_var, font=("Segoe UI", 10), wraplength=500, justify="left",
        ).pack(anchor="w", pady=(6, 10), fill="x")

        self.progress = ttk.Progressbar(outer, mode="indeterminate")
        self.progress.pack(fill="x", pady=(0, 14))
        self.progress.start(12)

        log_frame = tk.Frame(outer)
        log_frame.pack(fill="both", expand=True, pady=(0, 14))
        self.log_text = tk.Text(
            log_frame, height=10, font=("Consolas", 9), bg="#1e1e1e", fg="#d4d4d4",
            wrap="word", state="disabled", borderwidth=0,
        )
        scrollbar = ttk.Scrollbar(log_frame, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scrollbar.set)
        self.log_text.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        button_row = tk.Frame(outer)
        button_row.pack(fill="x")
        self.open_button = tk.Button(button_row, text="Open rapport", command=self._open_app, state="disabled")
        self.open_button.pack(side="left")
        self.retry_button = tk.Button(button_row, text="Retry", command=self._retry, state="disabled")
        self.retry_button.pack(side="left", padx=(8, 0))
        self.close_button = tk.Button(button_row, text="Close", command=self._on_close)
        self.close_button.pack(side="right")

    def _log(self, text: str) -> None:
        self.log_text.configure(state="normal")
        self.log_text.insert("end", text + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _start_worker(self) -> None:
        self.retry_button.configure(state="disabled")
        self.open_button.configure(state="disabled")
        self.progress.configure(mode="indeterminate")
        self.progress.start(12)
        threading.Thread(target=self._run_bootstrap, daemon=True).start()

    def _retry(self) -> None:
        self._start_worker()

    def _run_bootstrap(self) -> None:
        writer = _QueueWriter(self._queue)
        old_stdout = sys.stdout
        sys.stdout = writer  # type: ignore[assignment]
        try:
            ok = self._bootstrap()
        finally:
            sys.stdout = old_stdout
        self._queue.put(("done" if ok else "error", ""))

    def _bootstrap(self) -> bool:
        self._queue.put(("status", "Checking Docker…"))
        if not docker_daemon_running():
            if docker_cli_available():
                print("Docker is installed but the daemon isn't running yet.")
            self._queue.put(("status", "Installing Docker Desktop — this can take several minutes…"))
            if not install_docker():
                self._queue.put((
                    "status",
                    "Couldn't get Docker running automatically. Please install Docker manually from "
                    "docker.com/get-started, make sure it's running, then click Retry.",
                ))
                return False

        self._queue.put(("status", "Docker is ready. Writing configuration…"))
        compose_path = write_compose_file()
        prefix = docker_cmd_prefix()

        self._queue.put(("status", "Pulling rapport images — this can take a few minutes the first time…"))
        pull = subprocess.run(prefix + ["compose", "-f", str(compose_path), "pull"], **_SUBPROCESS_KWARGS)
        if pull.returncode != 0:
            self._queue.put(("status", "Failed to pull rapport images. Check your internet connection, then click Retry."))
            return False

        self._queue.put(("status", "Starting rapport…"))
        up = subprocess.run(prefix + ["compose", "-f", str(compose_path), "up", "-d"], **_SUBPROCESS_KWARGS)
        if up.returncode != 0:
            self._queue.put(("status", "Failed to start rapport. Click Retry, or check `docker compose logs` for details."))
            return False

        self._queue.put(("status", "Waiting for rapport to become ready…"))
        if not wait_for_healthy():
            self._queue.put(("status", "rapport didn't become healthy in time. Click Retry, or check `docker compose logs`."))
            return False

        self._queue.put(("status", f"rapport is running! Opening {APP_URL} in your browser…"))
        open_app()
        return True

    def _drain_queue(self) -> None:
        try:
            while True:
                kind, text = self._queue.get_nowait()
                if kind == "log":
                    self._log(text)
                elif kind == "status":
                    self.status_var.set(text)
                elif kind == "done":
                    self._on_finished(True)
                elif kind == "error":
                    self._on_finished(False)
        except queue.Empty:
            pass
        self.root.after(_POLL_MS, self._drain_queue)

    def _on_finished(self, ok: bool) -> None:
        self.progress.stop()
        self.progress.configure(mode="determinate")
        self.progress["value"] = 100 if ok else 0
        if ok:
            self.open_button.configure(state="normal")
            self.status_var.set(
                "rapport is running! You can close this window — it keeps running in the "
                "background (managed by Docker) and restarts automatically with your computer."
            )
        else:
            self.retry_button.configure(state="normal")

    def _open_app(self) -> None:
        open_app()

    def _on_close(self) -> None:
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


def main() -> int:
    InstallerWindow().run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
