from pathlib import Path

from renglo_cli.peer import list_peers, show


def test_peer_list_and_show(workspace: Path) -> None:
    listed = list_peers(workspace)
    ids = [p["id"] for p in listed["peers"]]
    assert "lab" in ids
    row = show(workspace, "lab")
    assert row["peer"]["id"] == "lab"
    assert "arbitiumlab" in row["peer"]["extensions"]
