from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from renglo_cli.aws import resolve_aws, ssm_parameter
from renglo_cli.errors import RengloError
from renglo_cli.run import run
from renglo_cli.workspace import bootstrap_install, env_name, ops_dir, require_platform

PLATFORM_VAR_STAGES = ("staging", "production")
# Shown first in text output; remaining VARS keys follow alphabetically.
PLATFORM_VAR_PRIORITY = (
    "FROM_EMAIL",
    "FE_BASE_URL",
    "BASE_URL",
    "AMPLIFY_CONSOLE_URL",
    "WEBSOCKET_URL",
)


def _platform_var_keys(vars_block: dict[str, Any]) -> list[str]:
    keys = [str(k) for k in vars_block.keys()]
    ordered = [key for key in PLATFORM_VAR_PRIORITY if key in vars_block]
    ordered.extend(sorted(key for key in keys if key not in PLATFORM_VAR_PRIORITY))
    return ordered


def _load_platform_vars(
    profile: str,
    region: str,
    env: str,
    stage: str,
) -> dict[str, Any]:
    parameter = f"/{env}/bootstrap/platform-vars/{stage}"
    raw = ssm_parameter(profile, region, parameter)
    vars_raw = (raw or {}).get("VARS") if isinstance(raw, dict) else {}
    vars_block: dict[str, Any] = {}
    if isinstance(vars_raw, dict):
        vars_block = {str(k): v for k, v in vars_raw.items()}
    return {
        "parameter": parameter,
        "present": bool(raw),
        "vars": vars_block,
        "var_keys": _platform_var_keys(vars_block),
    }


def format_state_show_text(data: dict[str, Any]) -> str:
    lines: list[str] = [str(data.get("env") or "")]
    for stage in PLATFORM_VAR_STAGES:
        block = (data.get("stages") or {}).get(stage) or {}
        lines.append(str(block.get("parameter") or f"/…/platform-vars/{stage}"))
        if not block.get("present"):
            lines.append("  (not registered — run renglo state write)")
            continue
        vars_block = block.get("vars") or {}
        for key in block.get("var_keys") or _platform_var_keys(vars_block):
            lines.append(f"  {key}: {vars_block.get(key)}")
    return "\n".join(lines)


def show(
    workspace: Path,
    *,
    profile: str = "",
    region: str = "",
) -> dict[str, Any]:
    require_platform(workspace)
    env = env_name(workspace)
    chosen_profile, chosen_region = resolve_aws(workspace, profile=profile, region=region)
    stages = {
        stage: _load_platform_vars(chosen_profile, chosen_region, env, stage)
        for stage in PLATFORM_VAR_STAGES
    }
    production = stages["production"]
    return {
        "ok": True,
        "env": env,
        "stages": stages,
        # Backward compatibility for JSON consumers expecting production only.
        "parameter": production["parameter"],
        "vars": production["vars"],
        "present": production["present"],
    }


def write(
    workspace: Path,
    *,
    profile: str = "",
    region: str = "",
    dry_run: bool = False,
) -> dict[str, Any]:
    require_platform(workspace)
    env = env_name(workspace)
    chosen_profile, chosen_region = resolve_aws(workspace, profile=profile, region=region)
    install = bootstrap_install(workspace)
    python = shutil.which("python3.12") or shutil.which("python3") or "python3"
    argv = [
        python,
        str(install),
        "write-state",
        "--env-name",
        env,
        "--aws-profile",
        chosen_profile,
        "--aws-region",
        chosen_region,
    ]
    if dry_run:
        argv.append("--dry-run")
    result = run(argv, cwd=ops_dir(workspace), dry_run=False if dry_run else dry_run)
    # When the operator asked for dry-run, pass through install.py --dry-run rather than skipping.
    if dry_run:
        result["dry_run"] = True
    result["env"] = env
    result["next"] = "renglo state show"
    return result


def local_config(
    workspace: Path,
    *,
    profile: str = "",
    region: str = "",
    dry_run: bool = False,
) -> dict[str, Any]:
    require_platform(workspace)
    env = env_name(workspace)
    chosen_profile, chosen_region = resolve_aws(workspace, profile=profile, region=region)
    install = bootstrap_install(workspace)
    python = shutil.which("python3.12") or shutil.which("python3") or "python3"
    argv = [
        python,
        str(install),
        "write-local-config",
        "--env-name",
        env,
        "--aws-profile",
        chosen_profile,
        "--aws-region",
        chosen_region,
    ]
    if dry_run:
        argv.append("--dry-run")
    result = run(argv, cwd=ops_dir(workspace), dry_run=False)
    result["output"] = str(
        ops_dir(workspace) / "bootstrap" / "output" / env / "local-dev"
    )
    result["next"] = "copy local-dev/ into renglo-api and console (see local-dev/README.md)"
    return result
