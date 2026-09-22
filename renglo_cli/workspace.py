from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from renglo_cli.errors import RengloError
from renglo_cli.sheets import extension_path, system_path

_MISSING_CWD = (
    "current directory no longer exists; cd to the workspace root or pass --workspace"
)


def _cwd() -> Path:
    try:
        return Path.cwd().resolve()
    except FileNotFoundError:
        pwd = os.environ.get("PWD", "").strip()
        if pwd and Path(pwd).exists():
            return Path(pwd).resolve()
        raise RengloError(_MISSING_CWD) from None


def find_workspace(explicit: Path | None = None) -> Path:
    """Platform or monorepo root. Walks up from cwd; prefers an active sheet."""
    override = os.environ.get("RENGLO_WORKSPACE", "").strip()
    if explicit is not None:
        return explicit.expanduser().resolve()
    if override:
        return Path(override).expanduser().resolve()
    here = _cwd()
    for candidate in [here, *here.parents]:
        if system_path(candidate).is_file() or extension_path(candidate).is_file():
            return candidate
        if _is_monorepo(candidate) or _is_platform(candidate):
            return candidate
    raise RengloError(
        "workspace root not found (need bootstrap/ + launcher/, or ops/bootstrap + ops/launcher). "
        "Run from the workspace or pass --workspace."
    )


def _is_monorepo(path: Path) -> bool:
    return (path / "ops" / "bootstrap").is_dir() and (path / "ops" / "launcher").is_dir()


def _is_platform(path: Path) -> bool:
    return (path / "bootstrap").is_dir() and (path / "launcher").is_dir()


def layout(workspace: Path) -> str:
    if _is_monorepo(workspace):
        return "monorepo"
    if _is_platform(workspace):
        return "platform"
    raise RengloError(f"unrecognized workspace layout: {workspace}")


def ops_dir(workspace: Path) -> Path:
    kind = layout(workspace)
    if kind == "monorepo":
        return workspace / "ops"
    return workspace


def require_platform(workspace: Path) -> Path:
    """bootstrap + launcher (system / stack / state / email / admin)."""
    ops = ops_dir(workspace)
    if not (ops / "bootstrap").is_dir() or not (ops / "launcher").is_dir():
        raise RengloError(
            f"bootstrap and launcher not found under {ops}. "
            "system/stack/state/email/admin need that pair."
        )
    return ops


def require_helper(workspace: Path) -> Path:
    helper = ops_dir(workspace) / "bom-helper"
    if not helper.is_dir():
        raise RengloError(
            f"bom-helper not found at {helper}. "
            "extension/peer commands need the monorepo (or a workspace that clones bom-helper)."
        )
    return helper


def require_monorepo(workspace: Path) -> Path:
    """BOM + extensions/ + bom-helper."""
    if not (workspace / "extensions").is_dir():
        raise RengloError(
            "extensions/ not found. extension/peer/user invite (catalog) need the monorepo."
        )
    require_helper(workspace)
    return workspace


def launcher_config(workspace: Path) -> Path:
    return ops_dir(workspace) / "launcher" / "cdk" / "customer-config.json"


def launcher_example(workspace: Path) -> Path:
    return ops_dir(workspace) / "launcher" / "cdk" / "customer-config.example.json"


def load_customer_config(workspace: Path) -> dict[str, Any]:
    path = launcher_config(workspace)
    if not path.is_file():
        raise RengloError(f"customer-config.json not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise RengloError(f"{path}: expected a JSON object")
    return data


def env_name(workspace: Path) -> str:
    cfg = load_customer_config(workspace)
    name = str(cfg.get("env_name", "")).strip()
    if not name:
        raise RengloError("customer-config.json: env_name is empty")
    return name


def find_bom_root(workspace: Path) -> Path:
    cfg = load_customer_config(workspace)
    github_repo = str(cfg.get("github_repo", "")).strip()
    checkout = github_repo.rstrip("/").split("/")[-1] if github_repo else ""
    ops = ops_dir(workspace)
    if checkout:
        candidate = ops / checkout
        if (candidate / "deploy_targets.yml").is_file():
            return candidate
    matches = sorted(p.parent for p in ops.glob("*-bom/deploy_targets.yml") if p.is_file())
    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise RengloError(f"no *-bom/deploy_targets.yml under {ops}")
    raise RengloError(
        "multiple BOM repos: " + ", ".join(p.name for p in matches) + "; set github_repo in customer-config.json"
    )


def deploy_targets_path(workspace: Path) -> Path:
    return find_bom_root(workspace) / "deploy_targets.yml"


def extension_folder(workspace: Path, handle: str) -> Path:
    handle = (handle or "").strip()
    folder = workspace / "extensions" / handle
    if not folder.is_dir():
        raise RengloError(f"extension folder not found: {folder}")
    return folder


def installer_manifest(folder: Path) -> Path:
    return folder / "installer" / "infra" / "cdk_extension.json"


def require_installer(workspace: Path, handle: str) -> Path:
    folder = extension_folder(workspace, handle)
    manifest = installer_manifest(folder)
    if not manifest.is_file():
        raise RengloError(
            f"{handle} is missing {manifest.relative_to(workspace)} "
            "(cdk_extension.json + policy JSON are required)"
        )
    policy_rel = ""
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
        policy_rel = str((data or {}).get("policy_file") or "").strip()
    except json.JSONDecodeError as exc:
        raise RengloError(f"{manifest}: invalid JSON ({exc})") from exc
    if policy_rel:
        policy = folder / "installer" / "infra" / policy_rel
        if not policy.is_file():
            raise RengloError(f"{handle} policy_file not found: {policy}")
    return folder


def gitconvoy_toml(folder: Path) -> Path:
    return folder / "gitconvoy.toml"


def read_repo_role(folder: Path) -> str:
    path = gitconvoy_toml(folder)
    if not path.is_file():
        return "product"
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if line.startswith("role"):
            _, _, value = line.partition("=")
            role = value.strip().strip("'\"")
            return role or "product"
    return "product"


def write_repo_role(folder: Path, role: str) -> Path:
    path = gitconvoy_toml(folder)
    text = (
        "# git-convoy membership marker (repo root).\n"
        "# role: product | aux | bom | incubating\n"
        f'role = "{role}"\n'
    )
    path.write_text(text, encoding="utf-8")
    return path


def helper_root(workspace: Path) -> Path:
    return require_helper(workspace)


def helper_venv_python(workspace: Path) -> Path:
    """bom-helper venv interpreter. Peer CDK / wheel build live there."""
    helper = helper_root(workspace)
    names = [n for n in (os.environ.get("BOM_VENV_NAME"), "bom-venv", "venv") if n]
    for name in names:
        candidate = helper / name / "bin" / "python"
        if candidate.is_file():
            return candidate
    return helper / names[0] / "bin" / "python"


def bootstrap_dir(workspace: Path) -> Path:
    return ops_dir(workspace) / "bootstrap"


def bootstrap_install(workspace: Path) -> Path:
    path = bootstrap_dir(workspace) / "install.py"
    if not path.is_file():
        raise RengloError(f"bootstrap install.py not found: {path}")
    return path


def bootstrap_venv_python(workspace: Path) -> Path:
    return bootstrap_dir(workspace) / "venv" / "bin" / "python"


def cdk_out_dir(workspace: Path, env: str) -> Path:
    return bootstrap_dir(workspace) / "output" / env / "cdk"


def ensure_gitignore(workspace: Path) -> Path:
    path = workspace / ".gitignore"
    line = ".renglo/"
    if path.exists():
        text = path.read_text(encoding="utf-8")
        if line.rstrip("/") not in text:
            if text and not text.endswith("\n"):
                text += "\n"
            path.write_text(text + line + "\n", encoding="utf-8")
    else:
        path.write_text(line + "\n", encoding="utf-8")
    return path
