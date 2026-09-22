from pathlib import Path

import pytest

from renglo_cli.emailcmd import allow_status


def test_email_list(workspace: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, ...]] = []

    def fake_aws(profile: str, region: str, *args: str, allow_fail: bool = False):
        calls.append(args)
        if args[:2] == ("ses", "list-identities"):
            return {"Identities": ["teammate@example.com", "example.com", "ops@example.com"]}
        if args[:2] == ("ses", "get-identity-verification-attributes"):
            return {
                "VerificationAttributes": {
                    "teammate@example.com": {"VerificationStatus": "Pending"},
                    "ops@example.com": {"VerificationStatus": "Success"},
                    "example.com": {"VerificationStatus": "Success"},
                }
            }
        if args[:2] == ("sesv2", "get-account"):
            return {"ProductionAccessEnabled": False}
        return None

    monkeypatch.setattr("renglo_cli.emailcmd.aws_json", fake_aws)
    data = allow_status(workspace, profile="acme-test", region="us-east-1")
    assert data["ok"] is True
    assert data["sandbox"] is True
    by_name = {row["identity"]: row for row in data["identities"]}
    assert by_name["teammate@example.com"] == {
        "identity": "teammate@example.com",
        "type": "email",
        "status": "Pending",
    }
    assert by_name["example.com"]["type"] == "domain"
    assert any(args[:2] == ("ses", "list-identities") for args in calls)
