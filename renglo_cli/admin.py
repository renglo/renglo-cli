from __future__ import annotations

from pathlib import Path
from typing import Any

from renglo_cli.aws import aws_json, resolve_aws, ssm_parameter, stack_outputs
from renglo_cli.errors import RengloError
from renglo_cli.workspace import env_name, require_platform


def _pool_id(workspace: Path, profile: str, region: str, env: str) -> str:
    outs = stack_outputs(profile, region, f"{env}-stack-a")
    pool = outs.get("UserPoolId") or ""
    if not pool:
        raise RengloError(f"{env}-stack-a has no UserPoolId output")
    return pool


def _setup_url(workspace: Path, profile: str, region: str, env: str, email: str) -> str:
    ssm = ssm_parameter(profile, region, f"/{env}/bootstrap/platform-vars/production")
    fe = ""
    if isinstance(ssm, dict):
        vars_block = ssm.get("VARS") or {}
        fe = str(vars_block.get("FE_BASE_URL") or vars_block.get("AMPLIFY_CONSOLE_URL") or "").strip()
    if fe and not fe.startswith("http://127.0.0.1"):
        base = fe.rstrip("/")
    else:
        base = "http://127.0.0.1:5174"
    return f"{base}/invite?setup=admin&email={email}"


def create(
    workspace: Path,
    email: str,
    *,
    profile: str = "",
    region: str = "",
    dry_run: bool = False,
) -> dict[str, Any]:
    require_platform(workspace)
    addr = (email or "").strip()
    if not addr or "@" not in addr:
        raise RengloError("admin create requires an email address")
    env = env_name(workspace)
    chosen_profile, chosen_region = resolve_aws(workspace, profile=profile, region=region)
    pool = _pool_id(workspace, chosen_profile, chosen_region, env)
    if not dry_run:
        aws_json(
            chosen_profile,
            chosen_region,
            "cognito-idp",
            "admin-create-user",
            "--user-pool-id",
            pool,
            "--username",
            addr,
            "--user-attributes",
            f"Name=email,Value={addr}",
            "Name=email_verified,Value=true",
            "--desired-delivery-mediums",
            "EMAIL",
        )
    url = _setup_url(workspace, chosen_profile, chosen_region, env, addr)
    return {
        "ok": True,
        "email": addr,
        "user_pool_id": pool,
        "setup_url": url,
        "local_setup_url": f"http://127.0.0.1:5174/invite?setup=admin&email={addr}",
        "dry_run": dry_run,
        "hint": "Cognito emails a temporary password. Complete setup at setup_url (or local_setup_url for Path B).",
        "next": "renglo email allow ADDRESS",
    }


def show(
    workspace: Path,
    email: str,
    *,
    profile: str = "",
    region: str = "",
) -> dict[str, Any]:
    require_platform(workspace)
    addr = (email or "").strip()
    if not addr:
        raise RengloError("admin show requires an email address")
    env = env_name(workspace)
    chosen_profile, chosen_region = resolve_aws(workspace, profile=profile, region=region)
    pool = _pool_id(workspace, chosen_profile, chosen_region, env)
    data = aws_json(
        chosen_profile,
        chosen_region,
        "cognito-idp",
        "admin-get-user",
        "--user-pool-id",
        pool,
        "--username",
        addr,
        allow_fail=True,
    )
    if not isinstance(data, dict) or not data.get("Username"):
        return {"ok": True, "email": addr, "exists": False, "user_pool_id": pool}
    attrs = {
        str(item.get("Name")): str(item.get("Value") or "")
        for item in (data.get("UserAttributes") or [])
        if isinstance(item, dict)
    }
    return {
        "ok": True,
        "email": addr,
        "exists": True,
        "user_pool_id": pool,
        "status": data.get("UserStatus"),
        "enabled": data.get("Enabled"),
        "attributes": {"email": attrs.get("email"), "email_verified": attrs.get("email_verified")},
    }
