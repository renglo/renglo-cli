from pathlib import Path

import pytest

from renglo_cli.admin import create
from renglo_cli.errors import RengloError


def test_admin_create_console_staging(platform: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("renglo_cli.admin.env_name", lambda workspace: "acme0922")
    monkeypatch.setattr(
        "renglo_cli.admin._pool_id",
        lambda workspace, profile, region, env: "us-east-1_pool",
    )
    monkeypatch.setattr(
        "renglo_cli.admin.show",
        lambda *args, **kwargs: {"exists": False},
    )
    updates: list[str] = []
    monkeypatch.setattr(
        "renglo_cli.admin._update_invite_template",
        lambda pool, profile, region, base_url, **kwargs: updates.append(base_url),
    )
    creates: list[tuple] = []
    monkeypatch.setattr(
        "renglo_cli.admin._create_user",
        lambda pool, profile, region, addr, **kwargs: creates.append((addr, kwargs)),
    )

    def fake_ssm(profile: str, region: str, name: str):
        if name.endswith("/staging"):
            return {"VARS": {"AMPLIFY_CONSOLE_URL": "https://staging.d1bb6bh3iwma4p.amplifyapp.com"}}
        return None

    monkeypatch.setattr("renglo_cli.admin.ssm_parameter", fake_ssm)
    data = create(
        platform,
        "admin@example.com",
        profile="p",
        region="us-east-1",
        console="staging",
    )
    assert data["console"] == "staging"
    assert data["action"] == "created"
    assert (
        data["setup_url"]
        == "https://staging.d1bb6bh3iwma4p.amplifyapp.com/invite?setup=admin&email=admin@example.com"
    )
    assert updates == ["https://staging.d1bb6bh3iwma4p.amplifyapp.com"]
    assert creates == [("admin@example.com", {})]


def test_admin_create_console_local(platform: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("renglo_cli.admin.env_name", lambda workspace: "acme0922")
    monkeypatch.setattr(
        "renglo_cli.admin._pool_id",
        lambda workspace, profile, region, env: "us-east-1_pool",
    )
    monkeypatch.setattr(
        "renglo_cli.admin.show",
        lambda *args, **kwargs: {"exists": False},
    )
    monkeypatch.setattr("renglo_cli.admin._update_invite_template", lambda *args, **kwargs: None)
    monkeypatch.setattr("renglo_cli.admin._create_user", lambda *args, **kwargs: None)
    data = create(
        platform,
        "admin@example.com",
        profile="p",
        region="us-east-1",
        console="local",
    )
    assert data["console"] == "local"
    assert "127.0.0.1:5174/invite?setup=admin" in data["setup_url"]


def test_admin_create_console_staging_missing(platform: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("renglo_cli.admin.env_name", lambda workspace: "acme0922")
    monkeypatch.setattr(
        "renglo_cli.admin._pool_id",
        lambda workspace, profile, region, env: "us-east-1_pool",
    )
    monkeypatch.setattr("renglo_cli.admin.ssm_parameter", lambda *args, **kwargs: None)
    with pytest.raises(RengloError, match="platform-vars/staging"):
        create(
            platform,
            "admin@example.com",
            profile="p",
            region="us-east-1",
            console="staging",
            dry_run=True,
        )


def test_admin_create_resends_pending_invite(platform: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("renglo_cli.admin.env_name", lambda workspace: "acme0922")
    monkeypatch.setattr(
        "renglo_cli.admin._pool_id",
        lambda workspace, profile, region, env: "us-east-1_pool",
    )
    monkeypatch.setattr(
        "renglo_cli.admin.show",
        lambda *args, **kwargs: {
            "exists": True,
            "status": "FORCE_CHANGE_PASSWORD",
        },
    )
    updates: list[str] = []
    monkeypatch.setattr(
        "renglo_cli.admin._update_invite_template",
        lambda pool, profile, region, base_url, **kwargs: updates.append(base_url),
    )
    resends: list[tuple] = []
    monkeypatch.setattr(
        "renglo_cli.admin._create_user",
        lambda pool, profile, region, addr, **kwargs: resends.append((addr, kwargs)),
    )

    def fake_ssm(profile: str, region: str, name: str):
        if name.endswith("/production"):
            return {"VARS": {"AMPLIFY_CONSOLE_URL": "https://production.d1bb6bh3iwma4p.amplifyapp.com/"}}
        return None

    monkeypatch.setattr("renglo_cli.admin.ssm_parameter", fake_ssm)
    data = create(
        platform,
        "admin@example.com",
        profile="p",
        region="us-east-1",
        console="production",
    )
    assert data["action"] == "resent"
    assert updates == ["https://production.d1bb6bh3iwma4p.amplifyapp.com"]
    assert resends == [("admin@example.com", {"message_action": "RESEND"})]
