from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

from renglo_cli.aws import caller_identity, resolve_aws
from renglo_cli.errors import RengloError
from renglo_cli.workspace import (
    bootstrap_venv_python,
    layout,
    ops_dir,
    require_platform,
)


def doctor(
    workspace: Path,
    *,
    profile: str = "",
    region: str = "",
) -> dict[str, Any]:
    require_platform(workspace)
    checks: list[dict[str, Any]] = []

    py = shutil.which("python3.12") or shutil.which("python3")
    py_ok = False
    py_detail = "python3.12 not on PATH"
    if py:
        ver = subprocess.run([py, "--version"], capture_output=True, text=True)
        py_detail = (ver.stdout or ver.stderr or "").strip() or py
        py_ok = "3.12" in py_detail or Path(py).name.startswith("python3.12")
    checks.append({"name": "python3.12", "ok": py_ok, "detail": py_detail})

    cdk = shutil.which("cdk")
    checks.append(
        {
            "name": "cdk",
            "ok": bool(cdk),
            "detail": cdk or "npm install -g aws-cdk",
        }
    )

    venv_py = bootstrap_venv_python(workspace)
    cdk_mod = False
    venv_detail = str(venv_py)
    if venv_py.is_file():
        probe = subprocess.run(
            [str(venv_py), "-c", "import aws_cdk"],
            capture_output=True,
            text=True,
        )
        cdk_mod = probe.returncode == 0
        venv_detail = f"{venv_py} aws_cdk={'ok' if cdk_mod else 'missing'}"
    else:
        venv_detail = f"missing {venv_py} — run bash bootstrap/setup-venvs.sh"
    checks.append({"name": "bootstrap_venv", "ok": venv_py.is_file() and cdk_mod, "detail": venv_detail})

    kind = layout(workspace)
    ops = ops_dir(workspace)
    checks.append(
        {
            "name": "workspace",
            "ok": True,
            "detail": f"{kind} root={workspace} ops={ops}",
        }
    )
    helper = ops / "bom-helper"
    checks.append(
        {
            "name": "bom-helper",
            "ok": helper.is_dir(),
            "optional": True,
            "detail": str(helper) if helper.is_dir() else "absent (needed for extension/peer)",
        }
    )

    sts_ok = False
    sts_detail = "skipped (no profile)"
    try:
        chosen_profile, chosen_region = resolve_aws(
            workspace, profile=profile, region=region, require_profile=False
        )
        if chosen_profile:
            ident = caller_identity(chosen_profile, chosen_region)
            sts_ok = bool(ident.get("account"))
            sts_detail = f"{ident.get('account')} {ident.get('arn')}"
        else:
            sts_detail = "pass --profile to check sts"
    except RengloError as exc:
        sts_detail = exc.message
    checks.append({"name": "aws_sts", "ok": sts_ok, "detail": sts_detail})

    required = [c for c in checks if not c.get("optional")]
    ok = all(c["ok"] for c in required)
    return {"ok": ok, "checks": checks, "workspace": str(workspace), "layout": kind}
