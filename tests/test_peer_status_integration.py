from pathlib import Path

import pytest

from renglo_cli.cli import main
from renglo_cli.stack import status as stack_status_cmd
from renglo_cli.status import status as overall_status


def test_stack_status_includes_peers(workspace: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_stack_status(profile: str, region: str, name: str) -> str:
        if name.endswith("-stack-a"):
            return "CREATE_COMPLETE"
        if name.endswith("-stack-b"):
            return "CREATE_COMPLETE"
        if name.endswith("-peer-lab"):
            return "UPDATE_COMPLETE"
        return "absent"

    monkeypatch.setattr("renglo_cli.stack.stack_status", fake_stack_status)
    monkeypatch.setattr("renglo_cli.peer.stack_status", fake_stack_status)
    data = stack_status_cmd(workspace, profile="acme-test", region="us-east-1")
    assert data["stacks"]["a"]["status"] == "CREATE_COMPLETE"
    assert len(data["peers"]) == 1
    assert data["peers"][0]["id"] == "lab"
    assert data["peers"][0]["status"] == "UPDATE_COMPLETE"


def test_renglo_status_includes_peers(workspace: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_stack_status(profile: str, region: str, name: str) -> str:
        if "peer" in name:
            return "absent"
        return "CREATE_COMPLETE"

    monkeypatch.setattr("renglo_cli.stack.stack_status", fake_stack_status)
    monkeypatch.setattr("renglo_cli.peer.stack_status", fake_stack_status)
    monkeypatch.setattr(
        "renglo_cli.status.ssm_parameter",
        lambda *args, **kwargs: {"VARS": {"FROM_EMAIL": "noreply@acme.test"}},
    )
    monkeypatch.setattr(
        "renglo_cli.status.stack_outputs",
        lambda *args, **kwargs: {"SesDnsMode": "domain", "FromEmail": "noreply@acme.test"},
    )
    data = overall_status(workspace, profile="acme-test", region="us-east-1")
    assert data["peers"][0]["id"] == "lab"
    assert data["peers"][0]["status"] == "absent"


def test_cli_peer_status(workspace: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    monkeypatch.setattr(
        "renglo_cli.peer.stack_status",
        lambda profile, region, name: "CREATE_COMPLETE",
    )
    assert main(
        ["--workspace", str(workspace), "--profile", "acme-test", "peer", "status"]
    ) == 0
    out = capsys.readouterr().out
    assert "acme0813-peer-lab" in out
    assert "CREATE_COMPLETE" in out
