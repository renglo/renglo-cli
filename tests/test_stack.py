from pathlib import Path

import pytest

from renglo_cli.errors import RengloError
from renglo_cli.stack import deploy, destroy


def test_destroy_requires_yes(workspace: Path) -> None:
    with pytest.raises(RengloError, match="--yes"):
        destroy(workspace, stacks=["b"], profile="p", yes=False)


def test_stack_deploy_dry_run(workspace: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AWS_PROFILE", "acme-test")
    data = deploy(
        workspace,
        stacks=["b"],
        profile="acme-test",
        region="us-east-1",
        create_github_oidc=False,
        write_state=False,
        dry_run=True,
    )
    assert data["dry_run"] is True
    assert any("stack-b" in c and "--exclusively" in c for c in data["commands"])
    assert all("stack-a" not in c for c in data["commands"])
