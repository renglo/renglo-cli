from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from renglo_cli.aws import aws_json, resolve_aws, ssm_parameter, stack_outputs
from renglo_cli.emailcmd import _production_access, _verification
from renglo_cli.errors import RengloError
from renglo_cli.workspace import env_name, require_platform


def _api_url(workspace: Path, profile: str, region: str, env: str, override: str) -> str:
    if (override or "").strip():
        return override.strip().rstrip("/")
    ssm = ssm_parameter(profile, region, f"/{env}/bootstrap/platform-vars/production")
    if isinstance(ssm, dict):
        base = str((ssm.get("VARS") or {}).get("BASE_URL") or "").strip()
        if base:
            return base.rstrip("/")
    return "http://127.0.0.1:5001"


def _client_id(profile: str, region: str, env: str) -> str:
    outs = stack_outputs(profile, region, f"{env}-stack-a")
    client = outs.get("AppClientId") or ""
    if not client:
        raise RengloError(f"{env}-stack-a has no AppClientId output")
    return client


def _id_token(
    profile: str,
    region: str,
    env: str,
    *,
    token: str,
    admin_email: str,
    admin_password: str,
) -> str:
    if (token or "").strip():
        return token.strip()
    email = (admin_email or "").strip()
    password = (admin_password or "").strip()
    if not email or not password:
        raise RengloError(
            "user invite needs --token or --admin-email plus --admin-password "
            "(no renglo auth login in v1)"
        )
    client = _client_id(profile, region, env)
    data = aws_json(
        profile,
        region,
        "cognito-idp",
        "initiate-auth",
        "--client-id",
        client,
        "--auth-flow",
        "USER_PASSWORD_AUTH",
        "--auth-parameters",
        f"USERNAME={email},PASSWORD={password}",
    )
    if not isinstance(data, dict):
        raise RengloError("cognito initiate-auth failed")
    if data.get("ChallengeName"):
        raise RengloError(
            f"admin user has Cognito challenge {data.get('ChallengeName')}; "
            "complete setup at /invite?setup=admin first"
        )
    id_token = ((data.get("AuthenticationResult") or {}) or {}).get("IdToken")
    if not id_token:
        raise RengloError("cognito initiate-auth returned no IdToken")
    return str(id_token)


def invite(
    workspace: Path,
    email: str,
    *,
    team: str,
    portfolio: str,
    api_url: str = "",
    token: str = "",
    admin_email: str = "",
    admin_password: str = "",
    profile: str = "",
    region: str = "",
    dry_run: bool = False,
) -> dict[str, Any]:
    require_platform(workspace)
    addr = (email or "").strip()
    team_id = (team or "").strip()
    portfolio_id = (portfolio or "").strip()
    if not addr or "@" not in addr:
        raise RengloError("user invite requires an email address")
    if not team_id or not portfolio_id:
        raise RengloError("user invite requires --team and --portfolio")
    env = env_name(workspace)
    chosen_profile, chosen_region = resolve_aws(workspace, profile=profile, region=region)
    prod = _production_access(chosen_profile, chosen_region)
    if prod is False:
        ver = _verification(chosen_profile, chosen_region, addr)
        if str(ver.get("status") or "") != "Success":
            raise RengloError(
                f"SES sandbox has not allowed {addr}. Run: renglo email allow {addr}"
            )
    base = _api_url(workspace, chosen_profile, chosen_region, env, api_url)
    url = f"{base}/_auth/user/invite"
    if dry_run:
        return {
            "ok": True,
            "dry_run": True,
            "url": url,
            "email": addr,
            "team_id": team_id,
            "portfolio_id": portfolio_id,
        }
    id_token = _id_token(
        chosen_profile,
        chosen_region,
        env,
        token=token,
        admin_email=admin_email,
        admin_password=admin_password,
    )
    body = json.dumps(
        {"email": addr, "team_id": team_id, "portfolio_id": portfolio_id}
    ).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {id_token}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
            status = resp.status
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        raise RengloError(f"invite failed ({exc.code}): {raw[-400:]}") from exc
    except urllib.error.URLError as exc:
        raise RengloError(
            f"could not reach {url}. Start the local API (Path B) or pass --api-url. {exc}"
        ) from exc
    try:
        parsed = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        parsed = {"raw": raw}
    return {
        "ok": True,
        "url": url,
        "http_status": status,
        "response": parsed,
        "email": addr,
    }
