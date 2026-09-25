from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from renglo_cli.aws import aws_bin, aws_json, resolve_aws, ssm_parameter, stack_outputs
from renglo_cli.errors import RengloError
from renglo_cli.workspace import env_name, require_platform

CONSOLE_TARGETS = ("local", "staging", "production")
_LOCAL_CONSOLE_BASE = "http://127.0.0.1:5174"
_RESEND_STATUSES = frozenset({"FORCE_CHANGE_PASSWORD", "UNCONFIRMED"})


def _fe_base_from_vars(vars_block: dict[str, Any]) -> str:
    return str(
        vars_block.get("FE_BASE_URL") or vars_block.get("AMPLIFY_CONSOLE_URL") or ""
    ).strip()


def _pool_id(workspace: Path, profile: str, region: str, env: str) -> str:
    outs = stack_outputs(profile, region, f"{env}-stack-a")
    pool = outs.get("UserPoolId") or ""
    if not pool:
        raise RengloError(f"{env}-stack-a has no UserPoolId output")
    return pool


def _console_base(
    profile: str,
    region: str,
    env: str,
    *,
    console: str = "",
) -> tuple[str, str]:
    """Return (base_url, console_target) for invite links."""
    target = (console or "").strip().lower()
    if target and target not in CONSOLE_TARGETS:
        raise RengloError(
            f"admin create --console must be one of: {', '.join(CONSOLE_TARGETS)}"
        )
    if target == "local":
        return _LOCAL_CONSOLE_BASE, "local"

    stage = target or "production"
    ssm = ssm_parameter(profile, region, f"/{env}/bootstrap/platform-vars/{stage}")
    fe = ""
    if isinstance(ssm, dict):
        vars_block = ssm.get("VARS") or {}
        if isinstance(vars_block, dict):
            fe = _fe_base_from_vars(vars_block)
    if target in ("staging", "production"):
        if not fe:
            raise RengloError(
                f"no console URL in /{env}/bootstrap/platform-vars/{target}; "
                "run renglo state show and finish BOM deploy first"
            )
        return fe.rstrip("/"), target

    # Legacy default: production SSM, localhost when unset or still a dev placeholder.
    if fe and not fe.startswith("http://127.0.0.1"):
        return fe.rstrip("/"), "production"
    return _LOCAL_CONSOLE_BASE, "local"


def _setup_url(
    workspace: Path,
    profile: str,
    region: str,
    env: str,
    email: str,
    *,
    console: str = "",
) -> tuple[str, str, str]:
    base, target = _console_base(profile, region, env, console=console)
    normalized = base.rstrip("/")
    return f"{normalized}/invite?setup=admin&email={email}", target, normalized


def _invite_message_template(base_url: str) -> dict[str, str]:
    setup_link = f"{base_url.rstrip('/')}/invite?setup=admin&email={{username}}"
    return {
        "EmailSubject": "Complete your admin account setup",
        "EmailMessage": (
            "Your admin account has been created.\n\n"
            "Email: {username}\n"
            "Temporary password (copy only the password below — not any punctuation after it):\n"
            "{####}\n\n"
            "Open this link to enter your name and set a new password:\n"
            f"{setup_link}\n"
        ),
        "SMSMessage": (
            "Admin account created. Username: {username}. "
            "Temporary password: {####}. "
            "Complete setup in the console invite screen."
        ),
    }


def _update_invite_template(
    pool: str,
    profile: str,
    region: str,
    base_url: str,
    *,
    dry_run: bool = False,
) -> None:
    payload = {
        "UserPoolId": pool,
        "AdminCreateUserConfig": {
            "AllowAdminCreateUserOnly": True,
            "InviteMessageTemplate": _invite_message_template(base_url),
        },
    }
    if dry_run:
        return
    with tempfile.NamedTemporaryFile("w", suffix=".json", encoding="utf-8", delete=False) as fh:
        json.dump(payload, fh)
        path = fh.name
    cmd = [
        aws_bin(),
        "cognito-idp",
        "update-user-pool",
        "--cli-input-json",
        f"file://{path}",
        "--output",
        "json",
    ]
    if profile:
        cmd.extend(["--profile", profile])
    if region:
        cmd.extend(["--region", region])
    result = subprocess.run(cmd, capture_output=True, text=True)
    Path(path).unlink(missing_ok=True)
    if result.returncode != 0:
        err = (result.stderr or result.stdout or "").strip()
        raise RengloError(f"aws cognito-idp update-user-pool failed: {err[-400:]}")


def _create_user(
    pool: str,
    profile: str,
    region: str,
    addr: str,
    *,
    message_action: str = "",
) -> None:
    args = [
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
    ]
    if message_action:
        args.extend(["--message-action", message_action])
    aws_json(profile, region, *args)


def _reset_password(pool: str, profile: str, region: str, addr: str) -> None:
    aws_json(
        profile,
        region,
        "cognito-idp",
        "admin-reset-user-password",
        "--user-pool-id",
        pool,
        "--username",
        addr,
    )


def create(
    workspace: Path,
    email: str,
    *,
    profile: str = "",
    region: str = "",
    console: str = "",
    dry_run: bool = False,
) -> dict[str, Any]:
    require_platform(workspace)
    addr = (email or "").strip()
    if not addr or "@" not in addr:
        raise RengloError("admin create requires an email address")
    env = env_name(workspace)
    chosen_profile, chosen_region = resolve_aws(workspace, profile=profile, region=region)
    pool = _pool_id(workspace, chosen_profile, chosen_region, env)
    url, console_target, console_base = _setup_url(
        workspace,
        chosen_profile,
        chosen_region,
        env,
        addr,
        console=console,
    )
    existing = show(
        workspace,
        addr,
        profile=chosen_profile,
        region=chosen_region,
    )
    action = "created"
    if existing.get("exists"):
        status = str(existing.get("status") or "")
        if status in _RESEND_STATUSES:
            action = "resent"
            if not dry_run:
                _update_invite_template(
                    pool,
                    chosen_profile,
                    chosen_region,
                    console_base,
                )
                _create_user(
                    pool,
                    chosen_profile,
                    chosen_region,
                    addr,
                    message_action="RESEND",
                )
        elif status == "CONFIRMED":
            action = "reset"
            if not dry_run:
                _update_invite_template(
                    pool,
                    chosen_profile,
                    chosen_region,
                    console_base,
                )
                _reset_password(pool, chosen_profile, chosen_region, addr)
        else:
            raise RengloError(
                f"admin {addr} already exists with status {status!r}; "
                "cannot resend invitation (expected FORCE_CHANGE_PASSWORD or CONFIRMED)"
            )
    elif not dry_run:
        _update_invite_template(
            pool,
            chosen_profile,
            chosen_region,
            console_base,
        )
        _create_user(pool, chosen_profile, chosen_region, addr)
    hint = (
        "Cognito emails a temporary password. Complete setup at setup_url "
        "(local_setup_url when using a laptop checkout)."
    )
    if action == "resent":
        hint = (
            "Existing admin invitation resent with the setup_url console base. "
            "Use the link in the new email or setup_url."
        )
    elif action == "reset":
        hint = (
            "Admin already completed setup once; Cognito sent a new temporary password. "
            "Sign in at setup_url (or /login on that console) and set a new password."
        )
    return {
        "ok": True,
        "email": addr,
        "user_pool_id": pool,
        "action": action,
        "user_status": existing.get("status") if existing.get("exists") else "NEW",
        "console": console_target,
        "setup_url": url,
        "local_setup_url": f"{_LOCAL_CONSOLE_BASE}/invite?setup=admin&email={addr}",
        "dry_run": dry_run,
        "hint": hint,
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
