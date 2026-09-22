from __future__ import annotations

from pathlib import Path
from typing import Any

from renglo_cli.errors import RengloError
from renglo_cli.extension.catalog import catalog_peers, load_targets
from renglo_cli.run import run
from renglo_cli.state import write as state_write
from renglo_cli.workspace import (
    env_name,
    find_bom_root,
    helper_root,
    require_helper,
)


def _script(workspace: Path) -> Path:
    script = helper_root(workspace) / "scripts" / "deploy_peer_cdk.sh"
    if not script.is_file():
        raise RengloError(f"deploy_peer_cdk.sh not found: {script}")
    return script


def list_peers(workspace: Path) -> dict[str, Any]:
    require_helper(workspace)
    bom = find_bom_root(workspace)
    data = load_targets(bom / "deploy_targets.yml")
    rows = catalog_peers(data)
    return {"ok": True, "env": env_name(workspace), "peers": rows}


def show(workspace: Path, peer_id: str) -> dict[str, Any]:
    require_helper(workspace)
    wanted = (peer_id or "").strip()
    if not wanted:
        raise RengloError("peer show requires a peer id")
    bom = find_bom_root(workspace)
    data = load_targets(bom / "deploy_targets.yml")
    for row in catalog_peers(data):
        if row["id"] == wanted:
            return {"ok": True, "env": env_name(workspace), "peer": row}
    raise RengloError(f"peers.{wanted} not in deploy_targets.yml")


def _peer_cmd(
    workspace: Path,
    action: str,
    peer_id: str,
    *,
    profile: str,
    dry_run: bool,
) -> dict[str, Any]:
    require_helper(workspace)
    wanted = (peer_id or "").strip()
    if not wanted:
        raise RengloError(f"peer {action} requires --peer-id")
    if action not in ("synth", "deploy", "destroy"):
        raise RengloError(f"unknown peer action: {action}")
    env = env_name(workspace)
    script = _script(workspace)
    helper = helper_root(workspace)
    argv = ["bash", str(script), action, "--peer-id", wanted]
    if profile:
        argv.extend(["--profile", profile])
    env_vars = {"ENV": env, "PEER_ID": wanted}
    if profile:
        env_vars["AWS_PROFILE"] = profile
    result = run(argv, cwd=helper, env=env_vars, dry_run=dry_run)
    result["env"] = env
    result["peer_id"] = wanted
    result["action"] = action
    return result


def synth(
    workspace: Path,
    peer_id: str,
    *,
    profile: str = "",
    dry_run: bool = False,
) -> dict[str, Any]:
    return _peer_cmd(workspace, "synth", peer_id, profile=profile, dry_run=dry_run)


def deploy(
    workspace: Path,
    peer_id: str,
    *,
    profile: str = "",
    region: str = "",
    write_state: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    result = _peer_cmd(workspace, "deploy", peer_id, profile=profile, dry_run=dry_run)
    if write_state:
        result["state"] = state_write(
            workspace, profile=profile, region=region, dry_run=dry_run
        )
    result["next"] = "renglo state write" if not write_state else "renglo peer show " + (peer_id or "")
    return result


def destroy(
    workspace: Path,
    peer_id: str,
    *,
    profile: str = "",
    yes: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    if not yes and not dry_run:
        raise RengloError("peer destroy requires --yes")
    return _peer_cmd(workspace, "destroy", peer_id, profile=profile, dry_run=dry_run)
