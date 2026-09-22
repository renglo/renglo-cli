from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from renglo_cli.aws import apply_to_env, resolve_aws
from renglo_cli.errors import RengloError
from renglo_cli.run import run
from renglo_cli.workspace import (
    bootstrap_install,
    bootstrap_venv_python,
    env_name,
    helper_root,
    ops_dir,
)


def plan_commands(workspace: Path, sheet: dict[str, Any]) -> list[str]:
    env = env_name(workspace)
    try:
        profile, region = resolve_aws(workspace, sheet=sheet, require_profile=True)
    except RengloError:
        profile, region = "<aws-profile>", "us-east-1"
    ops = ops_dir(workspace)
    path = str(sheet.get("path") or "")
    peer_id = str(sheet.get("peer_id") or "")
    cmds: list[str] = []
    if path == "hub":
        cmds.extend(
            [
                f"cd {ops} && python3.12 bootstrap/install.py synth",
                (
                    f"cd {ops}/bootstrap/output/{env}/cdk && "
                    f'cdk deploy "{env}-stack-b" --app "../../../venv/bin/python app.py" '
                    f"--output . --exclusively --require-approval never --profile {profile}"
                ),
            ]
        )
    else:
        cmds.extend(
            [
                f"cd {helper_root(workspace)} && bash scripts/deploy_peer_cdk.sh synth --peer-id {peer_id}",
                f"cd {helper_root(workspace)} && bash scripts/deploy_peer_cdk.sh deploy --peer-id {peer_id}",
            ]
        )
    cmds.append(
        f"cd {ops} && python3.12 bootstrap/install.py write-state "
        f"--env-name {env} --aws-profile {profile} --aws-region {region}"
    )
    return cmds


def run_deploy(workspace: Path, sheet: dict[str, Any], *, dry_run: bool = False) -> dict[str, Any]:
    commands = plan_commands(workspace, sheet)
    if dry_run:
        return {"ok": True, "dry_run": True, "commands": commands}
    env = env_name(workspace)
    profile, region = resolve_aws(workspace, sheet=sheet, require_profile=True)
    apply_to_env(profile, region)
    os.environ["ENV"] = env
    path = str(sheet.get("path") or "")
    if path == "hub":
        _run_hub(workspace, env, profile)
    else:
        _run_peer(workspace, str(sheet.get("peer_id") or ""), profile)
    _run_write_state(workspace, env, profile, region)
    return {"ok": True, "dry_run": False, "commands": commands, "stack": _stack_name(env, sheet)}


def _stack_name(env: str, sheet: dict[str, Any]) -> str:
    if str(sheet.get("path") or "") == "hub":
        return f"{env}-stack-b"
    return f"{env}-peer-{sheet.get('peer_id')}"


def _run_hub(workspace: Path, env: str, profile: str) -> None:
    install = bootstrap_install(workspace)
    run(["python3.12", str(install), "synth"], cwd=ops_dir(workspace))
    cdk_dir = ops_dir(workspace) / "bootstrap" / "output" / env / "cdk"
    app = bootstrap_venv_python(workspace)
    argv = [
        "cdk",
        "deploy",
        f"{env}-stack-b",
        "--app",
        f"{app} app.py" if app.is_file() else "python app.py",
        "--output",
        ".",
        "--exclusively",
        "--require-approval",
        "never",
        "--profile",
        profile,
    ]
    run(argv, cwd=cdk_dir)


def _run_peer(workspace: Path, peer_id: str, profile: str) -> None:
    if not peer_id:
        raise RengloError("sheet missing peer_id")
    from renglo_cli.peer import deploy as peer_deploy
    from renglo_cli.peer import synth as peer_synth

    peer_synth(workspace, peer_id, profile=profile)
    peer_deploy(workspace, peer_id, profile=profile, write_state=False)


def _run_write_state(workspace: Path, env: str, profile: str, region: str) -> None:
    from renglo_cli.state import write as state_write

    _ = env
    state_write(workspace, profile=profile, region=region)
