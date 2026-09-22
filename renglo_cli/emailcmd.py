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


def _identity_type(identity: str) -> str:
    return "email" if "@" in identity else "domain"


def _list_ses_identities(profile: str, region: str) -> list[str]:
    identities: list[str] = []
    token = ""
    while True:
        args = ["ses", "list-identities"]
        if token:
            args.extend(["--next-token", token])
        data = aws_json(profile, region, *args, allow_fail=True)
        if not isinstance(data, dict):
            break
        identities.extend(str(x) for x in (data.get("Identities") or []) if str(x).strip())
        token = str(data.get("NextToken") or "").strip()
        if not token:
            break
    return identities


def _verification_map(profile: str, region: str, identities: list[str]) -> dict[str, str]:
    statuses: dict[str, str] = {}
    batch = 64
    for i in range(0, len(identities), batch):
        chunk = identities[i : i + batch]
        data = aws_json(
            profile,
            region,
            "ses",
            "get-identity-verification-attributes",
            "--identities",
            *chunk,
            allow_fail=True,
        )
        attrs = (data.get("VerificationAttributes") or {}) if isinstance(data, dict) else {}
        for name in chunk:
            row = attrs.get(name) or {}
            statuses[name] = str(row.get("VerificationStatus") or "Unknown")
    return statuses


def _verification(profile: str, region: str, identity: str) -> dict[str, Any]:
    statuses = _verification_map(profile, region, [identity]) if identity else {}
    return {
        "identity": identity,
        "status": statuses.get(identity) or "Unknown",
    }


def _production_access(profile: str, region: str) -> bool | None:
    data = aws_json(profile, region, "sesv2", "get-account", allow_fail=True)
    if isinstance(data, dict) and "ProductionAccessEnabled" in data:
        return bool(data.get("ProductionAccessEnabled"))
    return None


def sender_status(
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


def allow_status(
    workspace: Path,
    *,
    profile: str = "",
    region: str = "",
) -> dict[str, Any]:
    require_platform(workspace)
    env = env_name(workspace)
    chosen_profile, chosen_region = resolve_aws(workspace, profile=profile, region=region)
    names = _list_ses_identities(chosen_profile, chosen_region)
    statuses = _verification_map(chosen_profile, chosen_region, names)
    rows = [
        {
            "identity": name,
            "type": _identity_type(name),
            "status": statuses.get(name) or "Unknown",
        }
        for name in names
    ]
    rows.sort(key=lambda r: (r["type"] != "email", r["identity"]))
    prod = _production_access(chosen_profile, chosen_region)
    return {
        "ok": True,
        "env": env,
        "sandbox": (prod is False),
        "production_access": prod,
        "identities": rows,
        "hint": (
            "email rows are verify-email-identity (sandbox allow-list). "
            "Pending means the recipient has not clicked the SES mail yet."
            if prod is False
            else "SES production access is on; this list is identities, not a send allow-list."
        ),
    }
