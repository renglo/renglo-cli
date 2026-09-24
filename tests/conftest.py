from __future__ import annotations

import json
from pathlib import Path

import pytest


def platform_workspace(tmp_path: Path) -> Path:
    root = tmp_path / "platform"
    (root / "bootstrap").mkdir(parents=True)
    (root / "bootstrap" / "install.py").write_text("# stub\n", encoding="utf-8")
    cdk = root / "launcher" / "cdk"
    cdk.mkdir(parents=True)
    (cdk / "customer-config.example.json").write_text(
        json.dumps(
            {
                "env_name": "myenv",
                "github_repo": "MyOrg/my-bom-repo",
                "email_from": "noreply@example.com",
                "email_identity_type": "domain",
                "extension_path": "do-not-copy",
                "_comment": "example",
            }
        ),
        encoding="utf-8",
    )
    return root


def monorepo_workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "ws"
    (ws / "extensions" / "xyz" / "installer" / "infra").mkdir(parents=True)
    (ws / "extensions" / "xyz" / "installer" / "infra" / "cdk_extension.json").write_text(
        json.dumps({"policy_file": "actions_tt_policy.json", "policy_name": "{env}-xyz-actions"}),
        encoding="utf-8",
    )
    (ws / "extensions" / "xyz" / "installer" / "infra" / "actions_tt_policy.json").write_text(
        json.dumps({"Version": "2012-10-17", "Statement": []}),
        encoding="utf-8",
    )
    (ws / "extensions" / "xyz" / "package").mkdir(parents=True)
    (ws / "extensions" / "xyz" / "package" / "pyproject.toml").write_text(
        '[project]\nname = "xyz"\nversion = "0.0.1"\n',
        encoding="utf-8",
    )
    bom = ws / "ops" / "acme-bom"
    (bom / "bom").mkdir(parents=True)
    (bom / "peers_bom" / "lab").mkdir(parents=True)
    (bom / "deploy_targets.yml").write_text(
        """# catalog
bom: 0.1.8
console_bom: 0.1.8
hub:
  python:
    - renglo-data
packages:
  data:
    python: renglo-data
peers:
  lab:
    compute: fargate
    extensions: [arbitiumlab]
    python:
      - arbitium-lab
    peers_bom: 0.1.8
tenants:
  acme0813:
    aws_account: "111122223333"
""",
        encoding="utf-8",
    )
    pin = {
        "version": "v0.1.8",
        "python": {"renglo-lib": "0.0.5", "arbitium-wl": "0.0.3", "arbitium-lab": "0.0.7"},
        "repos": {},
    }
    (bom / "bom" / "v0.1.8.json").write_text(json.dumps(pin), encoding="utf-8")
    (bom / "peers_bom" / "lab" / "v0.1.8.json").write_text(json.dumps(pin), encoding="utf-8")
    (ws / "ops" / "bootstrap").mkdir(parents=True)
    (ws / "ops" / "bootstrap" / "install.py").write_text("# stub\n", encoding="utf-8")
    (ws / "ops" / "bom-helper" / "scripts").mkdir(parents=True)
    (ws / "ops" / "bom-helper" / "scripts" / "deploy_peer_cdk.sh").write_text(
        "#!/bin/bash\nexit 0\n", encoding="utf-8"
    )
    launch = ws / "ops" / "launcher" / "cdk"
    launch.mkdir(parents=True)
    (launch / "customer-config.json").write_text(
        json.dumps(
            {
                "env_name": "acme0813",
                "github_repo": "Acme/acme-bom",
                "aws_region": "us-east-1",
                "email_from": "noreply@acme.test",
                "email_identity_type": "domain",
            }
        ),
        encoding="utf-8",
    )
    return ws


@pytest.fixture
def platform(tmp_path: Path) -> Path:
    return platform_workspace(tmp_path)


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    return monorepo_workspace(tmp_path)
