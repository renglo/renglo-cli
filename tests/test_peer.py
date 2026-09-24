from pathlib import Path

import pytest

from renglo_cli.errors import RengloError
from renglo_cli.peer import collect_peer_statuses, list_peers, show, status


def test_peer_list_and_show(workspace: Path) -> None:
    listed = list_peers(workspace)
    ids = [p["id"] for p in listed["peers"]]
    assert "lab" in ids
    row = show(workspace, "lab")
    assert row["peer"]["id"] == "lab"
    assert "arbitiumlab" in row["peer"]["extensions"]


def test_peer_status_all_declared(workspace: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[str] = []

    def fake_stack_status(profile: str, region: str, name: str) -> str:
        seen.append(name)
        return "CREATE_COMPLETE" if name.endswith("-peer-lab") else "absent"

    monkeypatch.setattr("renglo_cli.peer.stack_status", fake_stack_status)
    rows = collect_peer_statuses(
        workspace, profile="acme-test", region="us-east-1"
    )
    assert len(rows) == 1
    assert rows[0]["id"] == "lab"
    assert rows[0]["name"] == "acme0813-peer-lab"
    assert rows[0]["status"] == "CREATE_COMPLETE"
    assert seen == ["acme0813-peer-lab"]

    data = status(workspace, profile="acme-test", region="us-east-1")
    assert data["env"] == "acme0813"
    assert data["peers"] == rows


def test_peer_status_unknown_peer(workspace: Path) -> None:
    with pytest.raises(RengloError, match="not in deploy_targets.yml"):
        collect_peer_statuses(
            workspace, profile="acme-test", region="us-east-1", peer_id="missing"
        )


def test_peer_status_without_profile(workspace: Path) -> None:
    rows = collect_peer_statuses(workspace, profile="", region="us-east-1")
    assert rows[0]["status"] == "unknown (pass --profile)"
