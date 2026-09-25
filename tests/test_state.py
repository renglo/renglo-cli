from pathlib import Path

import pytest

from renglo_cli.state import format_state_show_text, show


def test_state_show_includes_staging_and_production(
    platform: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake_ssm(profile: str, region: str, name: str):
        if name.endswith("/staging"):
            return {
                "VARS": {
                    "BASE_URL": "https://staging-api.example.com",
                    "AMPLIFY_CONSOLE_URL": "https://staging.console.example.com",
                    "FROM_EMAIL": "noreply@example.com",
                }
            }
        if name.endswith("/production"):
            return {
                "VARS": {
                    "BASE_URL": "https://api.example.com",
                    "ZZZ_LAST": "tail",
                }
            }
        return None

    monkeypatch.setattr("renglo_cli.state.ssm_parameter", fake_ssm)
    monkeypatch.setattr(
        "renglo_cli.state.env_name",
        lambda workspace: "acme0922",
    )
    data = show(platform, profile="acme-test", region="us-east-1")
    assert data["stages"]["staging"]["present"] is True
    assert data["stages"]["production"]["present"] is True
    assert data["vars"]["BASE_URL"] == "https://api.example.com"
    text = format_state_show_text(data)
    assert "platform-vars/staging" in text
    assert "staging-api.example.com" in text
    assert "platform-vars/production" in text
    assert "ZZZ_LAST" in text
