import json
from pathlib import Path

import pytest

from renglo_cli.aws import resolve_aws
from renglo_cli.cli import main
from renglo_cli.errors import RengloError
from renglo_cli.stack import parse_stacks
from renglo_cli.system import init, install_start, install_plan


def test_system_init_writes_config_without_extension_path(platform: Path) -> None:
    data = init(
        platform,
        env_name_flag="demo1",
        github_repo="Acme/demo-bom",
        email_from="noreply@demo.test",
        email_identity_type="domain",
        email_hosted_zone_id="Z123",
        enable_staging=False,
    )
    cfg = json.loads((platform / "launcher" / "cdk" / "customer-config.json").read_text())
    assert cfg["env_name"] == "demo1"
    assert cfg["github_repo"] == "Acme/demo-bom"
    assert cfg["email_from"] == "noreply@demo.test"
    assert "extension_path" not in cfg
    assert "compute_type" not in cfg
    assert "github_handlers_repo" not in cfg
    assert "ec2_instance_type" not in cfg
    assert "_comment" not in cfg
    assert data["next"].startswith("renglo system install start")
    assert (platform / ".gitignore").read_text().find(".renglo/") >= 0


def test_system_install_sheet(platform: Path) -> None:
    init(
        platform,
        env_name_flag="demo1",
        github_repo="Acme/demo-bom",
        email_from="noreply@demo.test",
        email_identity_type="email",
    )
    start = install_start(platform, profile="demo-profile", region="us-east-1")
    assert start["sheet"]["aws_profile"] == "demo-profile"
    profile, region = resolve_aws(platform)
    assert profile == "demo-profile"
    assert region == "us-east-1"
    plan = install_plan(platform)
    assert "synth" in plan["remaining"]
    assert "write-state" in plan["remaining"]


def test_parse_stacks() -> None:
    assert parse_stacks("a,b") == ["a", "b"]
    assert parse_stacks("b") == ["b"]
    with pytest.raises(RengloError):
        parse_stacks("c")


def test_cli_system_init(platform: Path) -> None:
    assert (
        main(
            [
                "--workspace",
                str(platform),
                "system",
                "init",
                "--env-name",
                "demo1",
                "--github-repo",
                "Acme/demo-bom",
                "--email-from",
                "noreply@demo.test",
                "--email-identity-type",
                "domain",
            ]
        )
        == 0
    )
