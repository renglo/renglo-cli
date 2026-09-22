from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from renglo_cli.aws import apply_to_env, caller_identity, resolve_aws
from renglo_cli.errors import RengloError
from renglo_cli.run import run
from renglo_cli.sheets import (
    SYSTEM_STEPS,
    mark_system_done,
    require_system,
    save_system,
    system_next,
)
from renglo_cli.stack import deploy as stack_deploy
from renglo_cli.stack import destroy as stack_destroy
from renglo_cli.stack import parse_stacks
from renglo_cli.state import write as state_write
from renglo_cli.workspace import (
    bootstrap_install,
    ensure_gitignore,
    env_name,
    launcher_config,
    load_customer_config,
    ops_dir,
    require_platform,
)


def init(
    workspace: Path,
    *,
    env_name_flag: str,
    github_repo: str,
    email_from: str,
    email_identity_type: str,
    email_hosted_zone_id: str = "",
    enable_staging: bool = False,
) -> dict[str, Any]:
    require_platform(workspace)
    env = (env_name_flag or "").strip()
    repo = (github_repo or "").strip()
    frm = (email_from or "").strip()
    ident = (email_identity_type or "").strip()
    if not env:
        raise RengloError("system init requires --env-name")
    if not repo:
        raise RengloError("system init requires --github-repo")
    if not frm:
        raise RengloError("system init requires --email-from")
    if ident not in ("domain", "email"):
        raise RengloError("--email-identity-type must be domain or email")

    dest = launcher_config(workspace)
    dest.parent.mkdir(parents=True, exist_ok=True)
    data: dict[str, Any] = {
        "env_name": env,
        "github_repo": repo,
        "email_from": frm,
        "email_identity_type": ident,
        "enable_staging": bool(enable_staging),
        "package_registry": {"domain_owners": []},
    }
    if email_hosted_zone_id.strip():
        data["email_hosted_zone_id"] = email_hosted_zone_id.strip()
    dest.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    ensure_gitignore(workspace)
    return {
        "ok": True,
        "wrote": str(dest),
        "env_name": env,
        "extension_path": None,
        "next": "renglo system install start --profile PROFILE",
    }


def synth(workspace: Path, *, dry_run: bool = False) -> dict[str, Any]:
    require_platform(workspace)
    install = bootstrap_install(workspace)
    ops = ops_dir(workspace)
    python = shutil.which("python3.12") or shutil.which("python3") or "python3"
    result = run([python, str(install), "synth"], cwd=ops, dry_run=dry_run)
    result["next"] = "renglo stack deploy --stack a  (or renglo system install apply)"
    return result


def cdk_bootstrap(
    workspace: Path,
    *,
    profile: str = "",
    region: str = "",
    dry_run: bool = False,
) -> dict[str, Any]:
    require_platform(workspace)
    chosen_profile, chosen_region = resolve_aws(workspace, profile=profile, region=region)
    apply_to_env(chosen_profile, chosen_region)
    ident = caller_identity(chosen_profile, chosen_region)
    account = ident.get("account") or ""
    if not account:
        raise RengloError("could not resolve AWS account for cdk bootstrap")
    target = f"aws://{account}/{chosen_region}"
    result = run(
        ["cdk", "bootstrap", target, "--profile", chosen_profile],
        cwd=ops_dir(workspace),
        dry_run=dry_run,
    )
    result["target"] = target
    result["next"] = "renglo stack deploy --stack a"
    return result


def destroy(
    workspace: Path,
    *,
    profile: str = "",
    region: str = "",
    yes: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    return stack_destroy(
        workspace,
        stacks=parse_stacks("a,b"),
        profile=profile,
        region=region,
        yes=yes,
        dry_run=dry_run,
    )


def install_start(
    workspace: Path,
    *,
    profile: str,
    region: str = "",
) -> dict[str, Any]:
    require_platform(workspace)
    if not (profile or "").strip():
        raise RengloError("system install start requires --profile")
    cfg = load_customer_config(workspace)
    env = env_name(workspace)
    chosen_profile, chosen_region = resolve_aws(
        workspace, profile=profile, region=region, require_profile=True
    )
    sheet = {
        "env": env,
        "aws_profile": chosen_profile,
        "aws_region": chosen_region,
        "config": str(launcher_config(workspace)),
        "github_repo": str(cfg.get("github_repo") or ""),
        "phase": "started",
        "done": [],
    }
    save_system(workspace, sheet)
    ensure_gitignore(workspace)
    return {
        "ok": True,
        "sheet": sheet,
        "next": "renglo system install plan",
    }


def install_plan(workspace: Path) -> dict[str, Any]:
    sheet = require_system(workspace)
    done = [str(x) for x in (sheet.get("done") or [])]
    remaining = [s for s in SYSTEM_STEPS if s not in done]
    return {
        "ok": True,
        "sheet": sheet,
        "done": done,
        "remaining": remaining,
        "phases": [
            "synth",
            "cdk-bootstrap",
            "OIDC auto-detect on stack-a",
            "stack-a",
            "stack-b",
            "write-state",
        ],
        "stops_before": ["email verify-sender", "admin create"],
        "next": system_next(sheet),
    }


def install_apply(
    workspace: Path,
    *,
    through: str = "write-state",
    dry_run: bool = False,
    profile: str = "",
    region: str = "",
) -> dict[str, Any]:
    sheet = require_system(workspace)
    stop = (through or "write-state").strip()
    if stop not in SYSTEM_STEPS:
        raise RengloError("--through must be one of " + ", ".join(SYSTEM_STEPS))
    chosen_profile, chosen_region = resolve_aws(
        workspace, profile=profile, region=region, sheet=sheet
    )
    done = [str(x) for x in (sheet.get("done") or [])]
    ran: list[str] = []
    results: list[dict[str, Any]] = []

    steps = {
        "synth": lambda: synth(workspace, dry_run=dry_run),
        "cdk-bootstrap": lambda: cdk_bootstrap(
            workspace, profile=chosen_profile, region=chosen_region, dry_run=dry_run
        ),
        "stack-a": lambda: stack_deploy(
            workspace,
            stacks=["a"],
            profile=chosen_profile,
            region=chosen_region,
            write_state=False,
            dry_run=dry_run,
        ),
        "stack-b": lambda: stack_deploy(
            workspace,
            stacks=["b"],
            profile=chosen_profile,
            region=chosen_region,
            write_state=False,
            dry_run=dry_run,
        ),
        "write-state": lambda: state_write(
            workspace, profile=chosen_profile, region=chosen_region, dry_run=dry_run
        ),
    }

    for step in SYSTEM_STEPS:
        if step in done:
            if step == stop:
                break
            continue
        results.append(steps[step]())
        ran.append(step)
        if not dry_run:
            mark_system_done(sheet, step)
            save_system(workspace, sheet)
        if step == stop:
            break

    return {
        "ok": True,
        "ran": ran,
        "done": sheet.get("done") or done,
        "results": results,
        "dry_run": dry_run,
        "next":         "renglo email verify-sender"
        if (not dry_run and "write-state" in (sheet.get("done") or []))
        else system_next(sheet),
    }
