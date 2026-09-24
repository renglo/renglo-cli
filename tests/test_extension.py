from pathlib import Path

from renglo_cli.extension.catalog_edit import (
    add_hub_python,
    add_new_peer,
    add_peer_extension,
    add_peer_python,
    ensure_package_slot,
    set_version_pointer,
)
from renglo_cli.extension.pin import bump_patch
from renglo_cli.extension import commands
from renglo_cli.sheets import save_extension


TARGETS = """# catalog
bom: 0.1.8
console_bom: 0.1.8
hub:
  python:
    - renglo-data
packages:
  data:
    python: renglo-data
peers:
  lab:
    compute: fargate
    extensions: [arbitiumlab]
    python:
      - arbitium-lab
    peers_bom: 0.1.8
tenants:
  acme0813:
    aws_account: "111122223333"
"""


def test_package_hub_peer_and_new_peer() -> None:
    text = ensure_package_slot(TARGETS, "xyz", "xyz")
    assert "  xyz:\n    python: xyz\n" in text
    text = add_hub_python(text, "xyz")
    assert "- xyz" in text.split("hub:")[1].split("packages:")[0]
    text = add_peer_extension(TARGETS, "lab", "xyz")
    assert "extensions: [arbitiumlab, xyz]" in text
    text = add_peer_python(TARGETS, "lab", "xyz")
    assert "- xyz" in text.split("peers:")[1]
    text = add_new_peer(
        TARGETS,
        peer_id="audio",
        handle="xyz",
        dist="xyz",
        compute="fargate",
        task_size="medium",
        peers_bom="0.1.8",
    )
    assert "  audio:" in text
    assert "extensions: [xyz]" in text
    assert text.index("  audio:") < text.index("tenants:")


def test_pointer_bump() -> None:
    text = set_version_pointer(TARGETS, "peers_bom", "0.1.9", peer_id="lab")
    assert "peers_bom: 0.1.9" in text
    assert bump_patch("0.1.8") == "0.1.9"


def test_place_config_pin_test_finish(workspace: Path) -> None:
    placed = commands.place(
        workspace,
        "xyz",
        hub=False,
        peer="lab",
        new_peer="",
        compute="fargate",
        task_size="medium",
        python_version="0.0.1",
        npm="",
        aws_profile="acme-test",
        aws_region="us-east-1",
    )
    assert placed["sheet"]["phase"] == "placed"
    assert placed["sheet"]["aws_profile"] == "acme-test"
    assert placed["next"] == "renglo extension install config"
    role = (workspace / "extensions" / "xyz" / "gitconvoy.toml").read_text()
    assert 'role = "incubating"' in role
    cfg = commands.config(workspace)
    catalog = (workspace / "ops" / "acme-bom" / "deploy_targets.yml").read_text()
    assert "extensions: [arbitiumlab, xyz]" in catalog
    assert "- xyz" in catalog
    assert cfg["sheet"]["phase"] == "configured"
    pinned = commands.pin(workspace, "0.0.1", "")
    assert pinned["pin"]["to"] == "0.1.9"
    assert (workspace / "ops" / "acme-bom" / "peers_bom" / "lab" / "v0.1.9.json").is_file()
    tested = commands.test(workspace, skip_synth=True)
    assert tested["ok"]
    assert tested["checks"]["unique_owner"] == "peer:lab"
    save_extension(
        workspace,
        {
            **commands.status(workspace)["sheet"],
            "phase": "pushed",
            "test": {"ok": True},
        },
    )
    finished = commands.finish(workspace)
    assert finished["role"] == "product"
    assert commands.status(workspace).get("sheet") is None
    assert 'role = "product"' in (workspace / "extensions" / "xyz" / "gitconvoy.toml").read_text()


def test_place_requires_profile(workspace: Path) -> None:
    try:
        commands.place(
            workspace,
            "xyz",
            hub=True,
            peer="",
            new_peer="",
            compute="fargate",
            task_size="medium",
            python_version="",
            npm="",
            aws_profile="",
        )
    except Exception as exc:
        assert "--profile" in str(exc)
    else:
        raise AssertionError("expected profile error")


def test_place_refuses_existing_catalog_handle(workspace: Path) -> None:
    infra = workspace / "extensions" / "arbitiumlab" / "installer" / "infra"
    infra.mkdir(parents=True)
    (infra / "cdk_extension.json").write_text('{"policy_file": "actions_tt_policy.json"}')
    (infra / "actions_tt_policy.json").write_text("{}")
    try:
        commands.place(
            workspace,
            "arbitiumlab",
            hub=False,
            peer="lab",
            new_peer="",
            compute="fargate",
            task_size="medium",
            python_version="",
            npm="",
            aws_profile="acme-test",
        )
    except Exception as exc:
        assert "already in the catalog" in str(exc)
    else:
        raise AssertionError("expected catalog error")
