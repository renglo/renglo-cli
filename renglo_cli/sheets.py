from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from renglo_cli.errors import RengloError

STATE_DIRNAME = ".renglo"
SYSTEM_FILENAME = "system.json"
EXTENSION_FILENAME = "extension.json"

EXTENSION_PHASES = (
    "placed",
    "configured",
    "pinned",
    "published",
    "deployed",
    "tested",
    "pushed",
)

EXTENSION_NEXT = {
    "placed": "renglo extension install config",
    "configured": "renglo extension install pin",
    "pinned": "renglo extension install publish",
    "published": "renglo extension install deploy",
    "deployed": "renglo extension install test",
    "tested": "renglo extension install push",
    "pushed": "renglo extension install finish",
}

SYSTEM_STEPS = (
    "synth",
    "cdk-bootstrap",
    "stack-a",
    "stack-b",
    "write-state",
)

SYSTEM_NEXT = {
    "started": "renglo system install apply",
    "synth": "renglo system install apply",
    "cdk-bootstrap": "renglo system install apply",
    "stack-a": "renglo system install apply",
    "stack-b": "renglo state write  (or renglo system install apply)",
    "write-state": "renglo email verify-sender",
}


def state_dir(workspace: Path) -> Path:
    return workspace / STATE_DIRNAME


def system_path(workspace: Path) -> Path:
    return state_dir(workspace) / SYSTEM_FILENAME


def extension_path(workspace: Path) -> Path:
    return state_dir(workspace) / EXTENSION_FILENAME


def _load(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else None


def load_system(workspace: Path) -> dict[str, Any] | None:
    return _load(system_path(workspace))


def load_extension(workspace: Path) -> dict[str, Any] | None:
    return _load(extension_path(workspace))


def require_system(workspace: Path) -> dict[str, Any]:
    data = load_system(workspace)
    if data is None:
        raise RengloError("no system install sheet. Run: renglo system install start")
    return data


def require_extension(workspace: Path) -> dict[str, Any]:
    data = load_extension(workspace)
    if data is None:
        raise RengloError(
            "nothing incubating. Run: renglo extension install place HANDLE --hub|--peer PEER|--new-peer PEER --profile PROFILE"
        )
    return data


def _save(path: Path, data: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    data["updated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def save_system(workspace: Path, data: dict[str, Any]) -> Path:
    return _save(system_path(workspace), data)


def save_extension(workspace: Path, data: dict[str, Any]) -> Path:
    return _save(extension_path(workspace), data)


def clear_system(workspace: Path) -> None:
    path = system_path(workspace)
    if path.is_file():
        path.unlink()


def clear_extension(workspace: Path) -> None:
    path = extension_path(workspace)
    if path.is_file():
        path.unlink()


def set_extension_phase(sheet: dict[str, Any], phase: str) -> dict[str, Any]:
    if phase not in EXTENSION_PHASES:
        raise RengloError(f"unknown phase: {phase}")
    sheet["phase"] = phase
    return sheet


def extension_next(sheet: dict[str, Any] | None) -> str:
    if not sheet:
        return "renglo extension install place HANDLE --hub|--peer PEER|--new-peer PEER --profile PROFILE"
    return EXTENSION_NEXT.get(str(sheet.get("phase") or ""), "renglo extension status")


def system_next(sheet: dict[str, Any] | None) -> str:
    if not sheet:
        return "renglo system init  (or renglo system install start)"
    done = [str(x) for x in (sheet.get("done") or [])]
    for step in SYSTEM_STEPS:
        if step not in done:
            if step == "synth":
                return "renglo system install apply"
            return "renglo system install apply"
    return SYSTEM_NEXT.get("write-state", "renglo email verify-sender")


def mark_system_done(sheet: dict[str, Any], step: str) -> dict[str, Any]:
    if step not in SYSTEM_STEPS:
        raise RengloError(f"unknown system step: {step}")
    done = [str(x) for x in (sheet.get("done") or [])]
    if step not in done:
        done.append(step)
    sheet["done"] = done
    sheet["phase"] = step
    return sheet
