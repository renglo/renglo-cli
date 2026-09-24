from __future__ import annotations

from pathlib import Path
from typing import Any

from renglo_cli.aws import (
    apply_to_env,
    describe_stack,
    github_oidc_present,
    resolve_aws,
    stack_name,
    stack_status,
)
from renglo_cli.errors import RengloError
from renglo_cli.peer import try_collect_peer_statuses
from renglo_cli.run import run
from renglo_cli.workspace import (
    bootstrap_venv_python,
    cdk_out_dir,
    env_name,
    require_platform,
)


def parse_stacks(value: str | list[str]) -> list[str]:
    if isinstance(value, list):
        parts = [str(p).strip().lower() for p in value if str(p).strip()]
    else:
        parts = [p.strip().lower() for p in str(value).replace(" ", "").split(",") if p.strip()]
    if not parts or any(p not in {"a", "b"} for p in parts):
        raise RengloError("--stack must be a, b, or a,b")
    # preserve order but unique
    seen: list[str] = []
    for part in parts:
        if part not in seen:
            seen.append(part)
    return seen


def status(
    workspace: Path,
    which: str = "",
    *,
    profile: str = "",
    region: str = "",
) -> dict[str, Any]:
    require_platform(workspace)
    env = env_name(workspace)
    chosen_profile, chosen_region = resolve_aws(workspace, profile=profile, region=region)
    wanted = parse_stacks(which or "a,b")
    stacks: dict[str, Any] = {}
    for letter in wanted:
        name = stack_name(env, letter)
        stacks[letter] = {
            "name": name,
            "status": stack_status(chosen_profile, chosen_region, name),
        }
    peers = try_collect_peer_statuses(
        workspace,
        profile=chosen_profile,
        region=chosen_region,
    )
    return {"ok": True, "env": env, "stacks": stacks, "peers": peers}


def _cdk_deploy_argv(
    workspace: Path,
    env: str,
    letter: str,
    profile: str,
    *,
    create_oidc: bool,
) -> tuple[list[str], Path]:
    cdk_dir = cdk_out_dir(workspace, env)
    app = bootstrap_venv_python(workspace)
    app_spec = f"{app} app.py" if app.is_file() else "python app.py"
    argv = [
        "cdk",
        "deploy",
        stack_name(env, letter),
        "--app",
        app_spec,
        "--output",
        ".",
        "--require-approval",
        "never",
        "--profile",
        profile,
    ]
    if letter == "b":
        argv.append("--exclusively")
    if letter == "a" and create_oidc:
        argv.extend(["--parameters", "CreateGitHubOIDC=true"])
    return argv, cdk_dir


def deploy(
    workspace: Path,
    *,
    stacks: list[str],
    profile: str = "",
    region: str = "",
    create_github_oidc: bool | None = None,
    write_state: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    require_platform(workspace)
    env = env_name(workspace)
    letters = parse_stacks(stacks)
    chosen_profile, chosen_region = resolve_aws(workspace, profile=profile, region=region)
    apply_to_env(chosen_profile, chosen_region)
    oidc = bool(create_github_oidc)
    if "a" in letters and create_github_oidc is None:
        oidc = not github_oidc_present(chosen_profile, chosen_region) if not dry_run else False
    commands: list[str] = []
    results: list[dict[str, Any]] = []
    for letter in letters:
        argv, cwd = _cdk_deploy_argv(
            workspace, env, letter, chosen_profile, create_oidc=oidc and letter == "a"
        )
        commands.append(" ".join(argv))
        if not dry_run and not cwd.is_dir():
            raise RengloError(f"CDK output missing: {cwd}. Run: renglo system synth")
        results.append(run(argv, cwd=cwd if cwd.is_dir() else workspace, dry_run=dry_run, env={"ENV": env}))
    payload: dict[str, Any] = {
        "ok": True,
        "env": env,
        "stacks": [stack_name(env, letter) for letter in letters],
        "create_github_oidc": oidc and "a" in letters,
        "write_state": write_state,
        "commands": commands,
        "results": results,
        "dry_run": dry_run,
    }
    if write_state:
        from renglo_cli.state import write as state_write

        payload["state"] = state_write(
            workspace, profile=chosen_profile, region=chosen_region, dry_run=dry_run
        )
    payload["next"] = "renglo state write" if not write_state else "renglo email sender-status"
    return payload


def destroy(
    workspace: Path,
    *,
    stacks: list[str],
    profile: str = "",
    region: str = "",
    yes: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    require_platform(workspace)
    if not yes and not dry_run:
        raise RengloError("stack destroy requires --yes")
    env = env_name(workspace)
    letters = parse_stacks(stacks)
    chosen_profile, chosen_region = resolve_aws(workspace, profile=profile, region=region)
    apply_to_env(chosen_profile, chosen_region)
    b_row = describe_stack(chosen_profile, chosen_region, stack_name(env, "b"))
    if letters == ["a"] and b_row:
        raise RengloError(
            "refuses A-before-B; destroy stack b first or pass --stack a,b"
        )
    order = ["b", "a"] if "a" in letters and "b" in letters else letters
    cdk_dir = cdk_out_dir(workspace, env)
    app = bootstrap_venv_python(workspace)
    app_spec = f"{app} app.py" if app.is_file() else "python app.py"
    commands: list[str] = []
    results: list[dict[str, Any]] = []
    for letter in order:
        argv = [
            "cdk",
            "destroy",
            stack_name(env, letter),
            "--app",
            app_spec,
            "--output",
            ".",
            "--force",
            "--profile",
            chosen_profile,
        ]
        commands.append(" ".join(argv))
        cwd = cdk_dir if cdk_dir.is_dir() else ops_dir_safe(workspace)
        results.append(run(argv, cwd=cwd, dry_run=dry_run))
    return {
        "ok": True,
        "env": env,
        "order": [stack_name(env, letter) for letter in order],
        "commands": commands,
        "results": results,
        "dry_run": dry_run,
    }


def ops_dir_safe(workspace: Path) -> Path:
    from renglo_cli.workspace import ops_dir

    return ops_dir(workspace)
