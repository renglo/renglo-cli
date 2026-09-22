from __future__ import annotations

import json
import os
import shutil
import subprocess
from typing import Any

from renglo_cli.errors import RengloError
from renglo_cli.workspace import load_customer_config


def resolve_aws(
    workspace,
    *,
    profile: str = "",
    region: str = "",
    sheet: dict[str, Any] | None = None,
    require_profile: bool = True,
) -> tuple[str, str]:
    """Profile/region from flags, then sheet, then env, then customer-config."""
    chosen_profile = (profile or "").strip()
    chosen_region = (region or "").strip()
    if sheet:
        if not chosen_profile:
            chosen_profile = str(sheet.get("aws_profile") or "").strip()
        if not chosen_region:
            chosen_region = str(sheet.get("aws_region") or "").strip()
    if not chosen_profile:
        chosen_profile = os.environ.get("AWS_PROFILE", "").strip()
    if not chosen_region:
        chosen_region = os.environ.get("AWS_REGION", "").strip() or os.environ.get("AWS_DEFAULT_REGION", "").strip()
    if not chosen_region:
        try:
            cfg = load_customer_config(workspace)
            chosen_region = str(cfg.get("aws_region") or "us-east-1").strip() or "us-east-1"
        except RengloError:
            chosen_region = "us-east-1"
    if require_profile and not chosen_profile:
        raise RengloError("AWS profile required — pass --profile (or set AWS_PROFILE)")
    return chosen_profile, chosen_region or "us-east-1"


def apply_to_env(profile: str, region: str) -> None:
    if profile:
        os.environ["AWS_PROFILE"] = profile
    if region:
        os.environ.setdefault("AWS_REGION", region)
        os.environ.setdefault("AWS_DEFAULT_REGION", region)


def aws_bin() -> str:
    exe = shutil.which("aws")
    if not exe:
        raise RengloError("aws CLI not found on PATH")
    return exe


def aws_json(profile: str, region: str, *args: str, allow_fail: bool = False) -> Any:
    cmd = [aws_bin(), *args, "--output", "json"]
    if profile:
        cmd.extend(["--profile", profile])
    if region:
        cmd.extend(["--region", region])
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        if allow_fail:
            return None
        err = (result.stderr or result.stdout or "").strip()
        raise RengloError(f"aws {' '.join(args)} failed: {err[-400:]}")
    text = (result.stdout or "").strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def stack_name(env: str, which: str) -> str:
    letter = which.strip().lower()
    if letter == "a":
        return f"{env}-stack-a"
    if letter == "b":
        return f"{env}-stack-b"
    raise RengloError(f"stack must be a or b, not {which!r}")


def describe_stack(profile: str, region: str, name: str) -> dict[str, Any] | None:
    data = aws_json(
        profile,
        region,
        "cloudformation",
        "describe-stacks",
        "--stack-name",
        name,
        allow_fail=True,
    )
    if not isinstance(data, dict):
        return None
    stacks = data.get("Stacks") or []
    if not stacks:
        return None
    row = stacks[0]
    return row if isinstance(row, dict) else None


def stack_outputs(profile: str, region: str, name: str) -> dict[str, str]:
    row = describe_stack(profile, region, name)
    if not row:
        raise RengloError(f"stack not found: {name}")
    out: dict[str, str] = {}
    for item in row.get("Outputs") or []:
        if not isinstance(item, dict):
            continue
        key = str(item.get("OutputKey") or "").strip()
        value = str(item.get("OutputValue") or "").strip()
        if key:
            out[key] = value
    return out


def stack_status(profile: str, region: str, name: str) -> str:
    row = describe_stack(profile, region, name)
    if not row:
        return "absent"
    return str(row.get("StackStatus") or "unknown")


def github_oidc_present(profile: str, region: str) -> bool:
    data = aws_json(profile, region, "iam", "list-open-id-connect-providers", allow_fail=True)
    if not isinstance(data, dict):
        return False
    for item in data.get("OpenIDConnectProviderList") or []:
        arn = ""
        if isinstance(item, dict):
            arn = str(item.get("Arn") or "")
        elif isinstance(item, str):
            arn = item
        if "token.actions.githubusercontent.com" in arn:
            return True
    return False


def caller_identity(profile: str, region: str) -> dict[str, str]:
    data = aws_json(profile, region, "sts", "get-caller-identity", allow_fail=True)
    if not isinstance(data, dict):
        raise RengloError("aws sts get-caller-identity failed — check --profile")
    return {
        "account": str(data.get("Account") or ""),
        "arn": str(data.get("Arn") or ""),
        "user_id": str(data.get("UserId") or ""),
    }


def ssm_parameter(profile: str, region: str, name: str) -> Any:
    data = aws_json(
        profile,
        region,
        "ssm",
        "get-parameter",
        "--name",
        name,
        allow_fail=True,
    )
    if not isinstance(data, dict):
        return None
    raw = ((data.get("Parameter") or {}) or {}).get("Value")
    if not raw:
        return None
    try:
        return json.loads(str(raw))
    except json.JSONDecodeError:
        return raw
