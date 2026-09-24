from __future__ import annotations

from pathlib import Path
from typing import Any

from renglo_cli.aws import resolve_aws, ssm_parameter, stack_outputs, stack_status
from renglo_cli.peer import try_collect_peer_statuses
from renglo_cli.sheets import (
    extension_next,
    load_extension,
    load_system,
    system_next,
)
from renglo_cli.workspace import env_name, launcher_config, require_platform


def status(
    workspace: Path,
    *,
    profile: str = "",
    region: str = "",
) -> dict[str, Any]:
    require_platform(workspace)
    payload: dict[str, Any] = {
        "ok": True,
        "workspace": str(workspace),
        "config": str(launcher_config(workspace)),
    }
    try:
        env = env_name(workspace)
        payload["env"] = env
    except Exception as exc:
        payload["env"] = None
        payload["env_error"] = str(exc)
        payload["next"] = "renglo system init"
        payload["hint"] = "customer-config.json missing or env_name empty"
        return payload

    system = load_system(workspace)
    extension = load_extension(workspace)
    payload["system_sheet"] = bool(system)
    payload["extension_sheet"] = bool(extension)
    if system:
        payload["system"] = {
            "phase": system.get("phase"),
            "done": system.get("done") or [],
            "next": system_next(system),
        }
    if extension:
        payload["extension"] = {
            "handle": extension.get("handle"),
            "phase": extension.get("phase"),
            "path": extension.get("path"),
            "peer_id": extension.get("peer_id"),
            "next": extension_next(extension),
        }

    try:
        chosen_profile, chosen_region = resolve_aws(
            workspace, profile=profile, region=region, sheet=system or extension, require_profile=False
        )
    except Exception:
        chosen_profile, chosen_region = "", "us-east-1"
    payload["aws_profile"] = chosen_profile or None
    payload["aws_region"] = chosen_region

    stacks: dict[str, Any] = {}
    if chosen_profile:
        stacks["a"] = stack_status(chosen_profile, chosen_region, f"{env}-stack-a")
        stacks["b"] = stack_status(chosen_profile, chosen_region, f"{env}-stack-b")
        ssm = ssm_parameter(
            chosen_profile,
            chosen_region,
            f"/{env}/bootstrap/platform-vars/production",
        )
        vars_block = {}
        if isinstance(ssm, dict):
            vars_block = ssm.get("VARS") or {}
        payload["ssm"] = {
            "FROM_EMAIL": vars_block.get("FROM_EMAIL"),
            "FE_BASE_URL": vars_block.get("FE_BASE_URL"),
            "BASE_URL": vars_block.get("BASE_URL"),
            "AMPLIFY_CONSOLE_URL": vars_block.get("AMPLIFY_CONSOLE_URL"),
        }
        try:
            outs = stack_outputs(chosen_profile, chosen_region, f"{env}-stack-a")
            payload["email"] = {
                "SesDnsMode": outs.get("SesDnsMode"),
                "FromEmail": outs.get("FromEmail"),
            }
        except Exception:
            payload["email"] = None
    else:
        stacks["a"] = "unknown (pass --profile)"
        stacks["b"] = "unknown (pass --profile)"
        payload["ssm"] = None
        payload["email"] = None
    payload["stacks"] = stacks
    payload["peers"] = try_collect_peer_statuses(
        workspace,
        profile=chosen_profile or "",
        region=chosen_region,
    )

    payload["next"] = _next(payload, system, extension)
    payload["hint"] = f"Next: {payload['next']}"
    return payload


def _next(payload: dict[str, Any], system, extension) -> str:
    if extension:
        return extension_next(extension)
    if system:
        return system_next(system)
    stacks = payload.get("stacks") or {}
    if stacks.get("a") in (None, "absent", "unknown (pass --profile)"):
        if not payload.get("env"):
            return "renglo system init"
        return "renglo system install start --profile PROFILE"
    if stacks.get("b") == "absent":
        return "renglo stack deploy --stack b"
    ssm = payload.get("ssm") or {}
    if not ssm.get("FROM_EMAIL") and ssm.get("FROM_EMAIL") is not None:
        return "renglo state write"
    if payload.get("ssm") is None:
        return "renglo state write"
    return "renglo help"
