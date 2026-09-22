from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from renglo_cli.errors import RengloError


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
    )


def commit_and_push_bom(
    bom_root: Path,
    *,
    message: str,
    paths: list[str],
    yes: bool,
    push: bool = True,
) -> dict[str, str]:
    if not (bom_root / ".git").exists() and not (bom_root / ".git").is_file():
        raise RengloError(f"{bom_root} is not a git repo")
    rels = [p for p in paths if (bom_root / p).exists() or p.endswith(".yml")]
    status = _git(bom_root, "status", "--porcelain")
    if status.returncode != 0:
        raise RengloError(status.stderr.strip() or "git status failed")
    dirty = [line[3:].strip() for line in status.stdout.splitlines() if line.strip()]
    extras = [p for p in dirty if p not in rels and not any(p.startswith(r.rstrip("/")) for r in rels)]
    if extras and not yes:
        raise RengloError(
            "BOM repo has unrelated dirty files: "
            + ", ".join(extras[:8])
            + ". Pass --yes to commit only the install paths, or clean the tree."
        )
    if not rels:
        raise RengloError("no BOM files to commit")
    add = _git(bom_root, "add", "--", *rels)
    if add.returncode != 0:
        raise RengloError(add.stderr.strip() or "git add failed")
    staged = _git(bom_root, "diff", "--cached", "--name-only")
    names = [n for n in staged.stdout.splitlines() if n.strip()]
    if not names:
        raise RengloError("nothing staged in the BOM repo")
    committed = _git(bom_root, "commit", "-m", message)
    if committed.returncode != 0:
        raise RengloError(committed.stderr.strip() or committed.stdout.strip() or "git commit failed")
    if push:
        pushed = _git(bom_root, "push", "origin", "HEAD")
        if pushed.returncode != 0:
            raise RengloError(pushed.stderr.strip() or "git push failed")
    return {"commit": "ok", "files": ", ".join(names), "pushed": "true" if push else "false"}


def convoy_init(workspace: Path) -> str:
    exe = shutil.which("git-convoy") or shutil.which("gitconvoy")
    if exe:
        result = subprocess.run(
            [exe, "init"],
            cwd=str(workspace),
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return f"git convoy init failed: {(result.stderr or result.stdout).strip()[:300]}"
        return "git convoy init ok"
    result = subprocess.run(
        ["git", "convoy", "init"],
        cwd=str(workspace),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return "git convoy not on PATH — run: git convoy init"
    return "git convoy init ok"
