from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

from renglo_cli.errors import RengloError


def run(
    argv: list[str],
    *,
    cwd: Path | str | None = None,
    env: dict[str, str] | None = None,
    dry_run: bool = False,
    capture: bool = False,
) -> dict[str, Any]:
    command = " ".join(argv)
    if dry_run:
        return {"ok": True, "dry_run": True, "command": command, "cwd": str(cwd or "")}
    merged = {**os.environ, **(env or {})}
    result = subprocess.run(
        argv,
        cwd=str(cwd) if cwd else None,
        env=merged,
        capture_output=capture,
        text=True,
    )
    if result.returncode != 0:
        extra = ""
        if capture:
            extra = " " + ((result.stderr or result.stdout or "").strip()[-400:])
        raise RengloError(f"command failed with exit {result.returncode}: {command}{extra}")
    payload: dict[str, Any] = {"ok": True, "dry_run": False, "command": command}
    if capture:
        payload["stdout"] = result.stdout or ""
        payload["stderr"] = result.stderr or ""
    return payload
