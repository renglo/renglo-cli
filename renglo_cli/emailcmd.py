from __future__ import annotations

from pathlib import Path
from typing import Any

from renglo_cli.aws import aws_json, resolve_aws, stack_outputs
from renglo_cli.errors import RengloError
from renglo_cli.workspace import env_name, load_customer_config, require_platform

SES_PRODUCTION_URL = (
    "https://docs.aws.amazon.com/ses/latest/dg/request-production-access.html"
)


def _from_address(workspace: Path, profile: str, region: str, env: str) -> tuple[str, str]:
    cfg = load_customer_config(workspace)
    frm = str(cfg.get("email_from") or "").strip()
    ident_type = str(cfg.get("email_identity_type") or "domain").strip() or "domain"
    try:
        outs = stack_outputs(profile, region, f"{env}-stack-a")
        frm = outs.get("FromEmail") or frm
        mode = outs.get("SesDnsMode") or ""
    except RengloError:
        mode = ""
        outs = {}
    return frm, mode or ident_type


def _identity_for(frm: str, mode: str) -> str:
    if mode in ("email", "email_inbox") or "@" in frm and mode != "domain" and "." not in mode:
        if mode in ("email", "email_inbox"):
            return frm
    if "@" in frm and mode not in ("email", "email_inbox"):
        return frm.split("@", 1)[-1]
    return frm


def _verification(profile: str, region: str, identity: str) -> dict[str, Any]:
    data = aws_json(
        profile,
        region,
        "ses",
        "get-identity-verification-attributes",
        "--identities",
        identity,
        allow_fail=True,
    )
    attrs = {}
    if isinstance(data, dict):
        attrs = (data.get("VerificationAttributes") or {}).get(identity) or {}
    return {
        "identity": identity,
        "status": str(attrs.get("VerificationStatus") or "Unknown"),
    }


def _production_access(profile: str, region: str) -> bool | None:
    data = aws_json(profile, region, "sesv2", "get-account", allow_fail=True)
    if isinstance(data, dict) and "ProductionAccessEnabled" in data:
        return bool(data.get("ProductionAccessEnabled"))
    return None


def status(
    workspace: Path,
    *,
    profile: str = "",
    region: str = "",
) -> dict[str, Any]:
    require_platform(workspace)
    env = env_name(workspace)
    chosen_profile, chosen_region = resolve_aws(workspace, profile=profile, region=region)
    frm, mode = _from_address(workspace, chosen_profile, chosen_region, env)
    identity = _identity_for(frm, mode)
    ver = _verification(chosen_profile, chosen_region, identity) if frm else {}
    prod = _production_access(chosen_profile, chosen_region)
    return {
        "ok": True,
        "env": env,
        "from_email": frm,
        "SesDnsMode": mode,
        "identity": identity,
        "verification": ver,
        "production_access": prod,
        "sandbox": (prod is False),
        "production_access_url": SES_PRODUCTION_URL,
        "next": "renglo email verify-sender"
        if str(ver.get("status") or "") != "Success"
        else "renglo admin create EMAIL",
    }


def verify_sender(
    workspace: Path,
    *,
    profile: str = "",
    region: str = "",
    dry_run: bool = False,
) -> dict[str, Any]:
    require_platform(workspace)
    env = env_name(workspace)
    chosen_profile, chosen_region = resolve_aws(workspace, profile=profile, region=region)
    frm, mode = _from_address(workspace, chosen_profile, chosen_region, env)
    if not frm:
        raise RengloError("email_from is empty; set it with renglo system init")
    identity = _identity_for(frm, mode)
    ver = _verification(chosen_profile, chosen_region, identity)
    resent = False
    if str(ver.get("status") or "") != "Success" and mode in ("email", "email_inbox"):
        if not dry_run:
            aws_json(
                chosen_profile,
                chosen_region,
                "ses",
                "verify-email-identity",
                "--email-address",
                frm,
            )
        resent = True
    return {
        "ok": True,
        "from_email": frm,
        "SesDnsMode": mode,
        "identity": identity,
        "verification": ver if not resent else {"identity": identity, "status": "Pending"},
        "resent_confirmation": resent,
        "dry_run": dry_run,
        "hint": "wait until VerificationStatus is Success; for manual_dns copy DkimRecord* CNAMEs",
        "next": "renglo admin create EMAIL",
    }


def allow(
    workspace: Path,
    address: str,
    *,
    profile: str = "",
    region: str = "",
    dry_run: bool = False,
) -> dict[str, Any]:
    require_platform(workspace)
    addr = (address or "").strip()
    if not addr or "@" not in addr:
        raise RengloError("email allow requires a recipient address")
    chosen_profile, chosen_region = resolve_aws(workspace, profile=profile, region=region)
    prod = _production_access(chosen_profile, chosen_region)
    if prod is True:
        return {
            "ok": True,
            "skipped": True,
            "reason": "SES production access already enabled",
            "address": addr,
        }
    if not dry_run:
        aws_json(
            chosen_profile,
            chosen_region,
            "ses",
            "verify-email-identity",
            "--email-address",
            addr,
        )
    ver = _verification(chosen_profile, chosen_region, addr)
    return {
        "ok": True,
        "address": addr,
        "verification": ver,
        "dry_run": dry_run,
        "hint": "recipient must click the SES confirmation link",
        "next": "renglo user invite EMAIL --team TEAM --portfolio PORTFOLIO",
    }
