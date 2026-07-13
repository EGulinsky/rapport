"""Windows service registration via Task Scheduler.

Creates a task that runs at login and restarts on failure. This is the
Windows equivalent of macOS launchd LaunchAgents.
"""
from __future__ import annotations

import subprocess

from agent.config import app_data_dir

TASK_NAME = "RapportAgent"


def is_registered() -> bool:
    try:
        result = subprocess.run(
            ["schtasks", "/query", "/tn", TASK_NAME],
            capture_output=True, timeout=10,
        )
        return result.returncode == 0
    except (subprocess.SubprocessError, FileNotFoundError):
        return False


def _task_xml(command: str, args: list[str]) -> str:
    log_dir = app_data_dir() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    arguments = " ".join(args)

    return f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <Triggers>
    <LogonTrigger>
      <Enabled>true</Enabled>
    </LogonTrigger>
  </Triggers>
  <Principals>
    <Principal>
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>true</StartWhenAvailable>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>false</Hidden>
    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
    <RestartOnFailure>
      <Interval>PT1M</Interval>
      <Count>999</Count>
    </RestartOnFailure>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>{command}</Command>
      <Arguments>{arguments}</Arguments>
    </Exec>
  </Actions>
</Task>"""


def register(command: str, args: list[str] | None = None) -> None:
    """Creates or updates the scheduled task.

    `command` is the executable (frozen .exe, or the Python interpreter for
    dev/source runs); `args` (e.g. ["-m", "agent.main"]) go into the task's
    separate <Arguments> element rather than being embedded in `command`."""
    xml_path = app_data_dir() / "task.xml"
    xml_path.write_text(_task_xml(command, args or []))

    # Delete existing task if present (ignoring errors)
    subprocess.run(
        ["schtasks", "/delete", "/tn", TASK_NAME, "/f"],
        capture_output=True, timeout=10,
    )

    subprocess.run(
        ["schtasks", "/create", "/tn", TASK_NAME, "/xml", str(xml_path)],
        capture_output=True, timeout=10,
    )
    xml_path.unlink(missing_ok=True)


def unregister() -> None:
    subprocess.run(
        ["schtasks", "/delete", "/tn", TASK_NAME, "/f"],
        capture_output=True, timeout=10,
    )
