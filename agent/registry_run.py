"""Windows service registration via the HKCU Run registry key.

Was originally Task Scheduler (schtasks /create), but that requires an
elevated/administrator token even for a task that only runs under the
current user's own session — confirmed on real Windows hardware: a normal
double-click launch (even by an account that's a member of Administrators)
runs under a UAC-filtered standard token, and schtasks /create fails with
"Access Denied" for that token regardless of the task's own trigger/principal.
schtasks's own stderr was being discarded (capture_output=True, return code
never checked), so the failure was invisible — is_registered() would just
report False forever and bootstrap_or_run() would loop on every launch
without ever starting the server.

The HKCU Run key is the standard no-elevation equivalent used by ordinary
tray/background apps, and mirrors launchd.py's user-level LaunchAgent and
systemd_service.py's `systemctl --user` (neither of those requires
elevation either).
"""
from __future__ import annotations

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "RapportAgent"


def _command_line(command: str, args: list[str]) -> str:
    quoted = f'"{command}"' if " " in command and not command.startswith('"') else command
    return quoted if not args else f"{quoted} {' '.join(args)}"


def is_registered() -> bool:
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.QueryValueEx(key, VALUE_NAME)
        return True
    except OSError:
        return False


def register(command: str, args: list[str] | None = None) -> None:
    """Creates or updates the HKCU Run value so the agent starts at login.

    `command` is the executable (frozen .exe, or the Python interpreter
    for dev/source runs); `args` (e.g. ["-m", "agent.tray"]) are appended
    to the command line rather than being embedded in `command`."""
    import winreg

    value = _command_line(command, args or [])
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
        winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, value)


def unregister() -> None:
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, VALUE_NAME)
    except OSError:
        pass
