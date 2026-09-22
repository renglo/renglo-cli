from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from renglo_cli.aws import resolve_aws, ssm_parameter
from renglo_cli.errors import RengloError
from renglo_cli.run import run
from renglo_cli.workspace import bootstrap_install, env_name, ops_dir, require_platform


def show(
    workspace: Path,
    *,
    profile: str = "",
    region: str = "",
) -> dict[str, Any]:
    require_platform(workspace)
    env = env_name(workspace)
    chosen_profile, chosen_region = resolve_aws(workspace, profile=profile, region=region)
    raw = ssm_parameter(
        chosen_profile,
        chosen_region,
        f"/{env}/bootstrap/platform-vars/production",
    )
    vars_block = (raw or {}).get("VARS") if isinstance(raw, dict) else {}
    keys = {
        "FROM_EMAIL": vars_block.get("FROM_EMAIL"),
        "FE_BASE_URL": vars_block.get("FE_BASE_URL"),
        "BASE_URL": vars_block.get("BASE_URL"),
        "AMPLIFY_CONSOLE_URL": vars_block.get("AMPLIFY_CONSOLE_URL"),
    }
    return {
        "ok": True,
        "env": env,
        "parameter": f"/{env}/bootstrap/platform-vars/production",
        "vars": keys,
        "present": bool(raw),
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
