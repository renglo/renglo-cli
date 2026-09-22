from pathlib import Path

import pytest

from renglo_cli.errors import RengloError
from renglo_cli.user import invite


def test_invite_requires_team_and_auth(workspace: Path) -> None:
    with pytest.raises(RengloError, match="--team"):
        invite(workspace, "a@b.com", team="", portfolio="p", profile="p")


def test_invite_dry_run(workspace: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("renglo_cli.user._production_access", lambda *a, **k: True)
    data = invite(
        workspace,
        "teammate@example.com",
        team="t1",
        portfolio="p1",
        profile="acme-test",
        api_url="http://127.0.0.1:5001",
        dry_run=True,
    )
    assert data["dry_run"] is True
    assert data["url"].endswith("/_auth/user/invite")
