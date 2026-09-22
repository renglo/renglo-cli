from pathlib import Path

from renglo_cli.workspace import find_workspace, layout, ops_dir


def test_finds_platform_layout(platform: Path) -> None:
    found = find_workspace(platform)
    assert layout(found) == "platform"
    assert ops_dir(found) == found


def test_finds_monorepo_layout(workspace: Path) -> None:
    found = find_workspace(workspace)
    assert layout(found) == "monorepo"
    assert ops_dir(found) == workspace / "ops"
