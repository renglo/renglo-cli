from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from renglo_cli.errors import RengloError
from renglo_cli.workspace import ops_dir

VALID_COMPUTE = ("lambda_only", "fargate", "ec2")


def _ensure_helper_scripts(bom_root: Path | None = None, workspace: Path | None = None) -> None:
    search: list[Path] = []
    if workspace is not None:
        try:
            search.append(ops_dir(workspace) / "bom-helper" / "scripts")
        except RengloError:
            pass
    if bom_root is not None:
        search.append(bom_root.parent / "bom-helper" / "scripts")
    here = Path(__file__).resolve()
    for parent in here.parents:
        search.append(parent / "bom-helper" / "scripts")
        search.append(parent / "ops" / "bom-helper" / "scripts")
    for scripts in search:
        if scripts.is_dir() and str(scripts) not in sys.path:
            sys.path.insert(0, str(scripts))
            return


try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None  # type: ignore[assignment]


def load_targets(path: Path) -> dict[str, Any]:
    if yaml is None:
        raise RengloError("PyYAML is required (renglo-cli venv: bash setup_venv.sh)")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise RengloError(f"{path}: expected a YAML object")
    return data


def _slots_from_helper(bom_root: Path):
    _ensure_helper_scripts(bom_root=bom_root)
    from catalog_slots import load_package_catalog, parse_package_catalog  # type: ignore

    return load_package_catalog(bom_root) or parse_package_catalog(
        (bom_root / "deploy_targets.yml").read_text(encoding="utf-8")
    ) or []


def slots(bom_root: Path) -> list[Any]:
    try:
        return _slots_from_helper(bom_root)
    except Exception:
        return []


def slot_for_handle(bom_root: Path, handle: str) -> Any | None:
    for slot in slots(bom_root):
        if getattr(slot, "id", None) == handle:
            return slot
    return None


def python_dist(bom_root: Path, handle: str) -> str:
    slot = slot_for_handle(bom_root, handle)
    if slot and getattr(slot, "python", None):
        return slot.python
    return handle.replace("_", "-")


def catalog_peers(data: dict[str, Any]) -> list[dict[str, Any]]:
    try:
        _ensure_helper_scripts()
        from peers import load_peers  # type: ignore

        return load_peers(data)
    except Exception:
        raw = data.get("peers") or {}
        if not isinstance(raw, dict):
            return []
        rows = []
        for peer_id, cfg in raw.items():
            if not isinstance(cfg, dict):
                continue
            exts = cfg.get("extensions") or []
            if not isinstance(exts, list):
                exts = []
            rows.append(
                {
                    "id": str(peer_id),
                    "extensions": [str(x).strip() for x in exts if str(x).strip()],
                    "compute": str(cfg.get("compute") or "fargate"),
                    "peers_bom": str(cfg.get("peers_bom") or cfg.get("handlers_bom") or ""),
                    "python": [str(x).strip() for x in (cfg.get("python") or [])],
                }
            )
        return rows


def owners_for_handle(data: dict[str, Any], handle: str, dist: str) -> list[str]:
    found: list[str] = []
    hub = (data.get("hub") or {}).get("python") or []
    if dist in {str(x).strip() for x in hub}:
        found.append("hub")
    for peer in catalog_peers(data):
        peer_python = peer.get("python") or []
        if not peer_python:
            peer_python = ((data.get("peers") or {}).get(peer["id"]) or {}).get("python") or []
        if handle in peer["extensions"] or dist in {str(x).strip() for x in peer_python}:
            if handle in peer["extensions"] and f"peer:{peer['id']}" not in found:
                found.append(f"peer:{peer['id']}")
    return found


def require_unique_place(
    data: dict[str, Any],
    *,
    handle: str,
    dist: str,
    path: str,
    peer_id: str,
) -> None:
    owners = owners_for_handle(data, handle, dist)
    want = "hub" if path == "hub" else f"peer:{peer_id}"
    others = [o for o in owners if o != want]
    if others:
        raise RengloError(
            f"{handle} is already placed on {', '.join(others)}; "
            "one owner only (hub or one peer)"
        )
    if path == "peer" and not any(p["id"] == peer_id for p in catalog_peers(data)):
        raise RengloError(f"peers.{peer_id} does not exist; use --new-peer {peer_id}")
    if path == "new-peer" and any(p["id"] == peer_id for p in catalog_peers(data)):
        raise RengloError(f"peers.{peer_id} already exists; use --peer {peer_id}")


def validate_compute(compute: str) -> str:
    value = (compute or "fargate").strip().lower()
    if value not in VALID_COMPUTE:
        raise RengloError(f"compute must be one of {', '.join(VALID_COMPUTE)}")
    return value


def current_bom_version(data: dict[str, Any], *, path: str, peer_id: str) -> str:
    if path == "hub":
        return str(data.get("bom") or "").strip().lstrip("v")
    for peer in catalog_peers(data):
        if peer["id"] == peer_id:
            return str(peer.get("peers_bom") or "").strip().lstrip("v")
    return str(data.get("bom") or "").strip().lstrip("v")


def pin_file(bom_root: Path, *, path: str, peer_id: str, version: str) -> Path:
    number = version.lstrip("v")
    if path == "hub":
        return bom_root / "bom" / f"v{number}.json"
    return bom_root / "peers_bom" / peer_id / f"v{number}.json"


def read_pin(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"version": f"v{path.stem.lstrip('v')}", "python": {}, "repos": {}}
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def tree_rows(data: dict[str, Any], catalog: list[Any]) -> list[dict[str, str]]:
    dist_to_id = {s.python: s.id for s in catalog if getattr(s, "python", None)}
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for dist in (data.get("hub") or {}).get("python") or []:
        handle = dist_to_id.get(str(dist).strip(), str(dist).strip())
        if handle in seen:
            continue
        seen.add(handle)
        rows.append({"handle": handle, "owner": "hub", "python": str(dist).strip()})
    for peer in catalog_peers(data):
        for handle in peer["extensions"]:
            if handle in seen:
                continue
            seen.add(handle)
            slot = next((s for s in catalog if getattr(s, "id", None) == handle), None)
            rows.append(
                {
                    "handle": handle,
                    "owner": f"peer:{peer['id']}",
                    "python": (slot.python if slot else handle),
                }
            )
    return rows
