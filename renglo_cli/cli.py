from __future__ import annotations

import argparse
import sys
from pathlib import Path

from renglo_cli import admin as admin_cmd
from renglo_cli import doctor as doctor_cmd
from renglo_cli import emailcmd
from renglo_cli import peer as peer_cmd
from renglo_cli import stack as stack_cmd
from renglo_cli import state as state_cmd
from renglo_cli import status as status_cmd
from renglo_cli import system as system_cmd
from renglo_cli import user as user_cmd
from renglo_cli.errors import RengloError
from renglo_cli.extension import commands as ext_cmd
from renglo_cli.help_text import format_help_text, help_payload
from renglo_cli.output import emit, fail
from renglo_cli.workspace import find_workspace


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    as_json = bool(getattr(args, "json", False))
    if not args.cmd or args.cmd == "help":
        topic = getattr(args, "topic", "") or ""
        emit(help_payload(topic), as_json, format_help_text(topic))
        return 0
    noun_cmd = {
        "system": "system_cmd",
        "stack": "stack_cmd",
        "state": "state_cmd",
        "email": "email_cmd",
        "admin": "admin_cmd",
        "user": "user_cmd",
        "extension": "extension_cmd",
        "peer": "peer_cmd",
    }.get(args.cmd)
    if noun_cmd and not getattr(args, noun_cmd, None):
        emit(help_payload(args.cmd), as_json, format_help_text(args.cmd))
        return 0
    if noun_cmd and getattr(args, noun_cmd, None) == "help":
        emit(help_payload(args.cmd), as_json, format_help_text(args.cmd))
        return 0
    if args.cmd == "extension" and getattr(args, "extension_cmd", None) == "install":
        inst = getattr(args, "extension_install_cmd", None)
        if not inst or inst == "help":
            emit(help_payload("extension"), as_json, format_help_text("extension"))
            return 0
    if args.cmd == "system" and getattr(args, "system_cmd", None) == "install":
        inst = getattr(args, "system_install_cmd", None)
        if not inst or inst == "help":
            emit(help_payload("system"), as_json, format_help_text("system"))
            return 0
    try:
        workspace = find_workspace(Path(args.workspace) if getattr(args, "workspace", None) else None)
        payload, text = _dispatch(workspace, args)
    except RengloError as exc:
        return fail(exc.message, as_json)
    emit(payload, as_json, text)
    if payload.get("ok") is False:
        return 1
    return 0


def _dispatch(workspace: Path, args: argparse.Namespace) -> tuple[dict, str]:
    profile = getattr(args, "profile", "") or ""
    region = getattr(args, "region", "") or ""
    cmd = args.cmd
    if cmd == "status":
        data = status_cmd.status(workspace, profile=profile, region=region)
        return data, _status_text(data)
    if cmd == "doctor":
        data = doctor_cmd.doctor(workspace, profile=profile, region=region)
        return data, _doctor_text(data)
    if cmd == "system":
        return _system(workspace, args, profile, region)
    if cmd == "stack":
        return _stack(workspace, args, profile, region)
    if cmd == "state":
        return _state(workspace, args, profile, region)
    if cmd == "email":
        return _email(workspace, args, profile, region)
    if cmd == "admin":
        return _admin(workspace, args, profile, region)
    if cmd == "user":
        return _user(workspace, args, profile, region)
    if cmd == "extension":
        return _extension(workspace, args)
    if cmd == "peer":
        return _peer(workspace, args, profile, region)
    raise RengloError(f"unknown command: {cmd}")


def _noun_help(topic: str) -> tuple[dict, str]:
    return help_payload(topic), format_help_text(topic)


def _system(workspace: Path, args, profile: str, region: str) -> tuple[dict, str]:
    sub = getattr(args, "system_cmd", None)
    if not sub or sub == "help":
        return _noun_help("system")
    dry = bool(getattr(args, "dry_run", False))
    if sub == "init":
        data = system_cmd.init(
            workspace,
            env_name_flag=args.env_name or "",
            github_repo=args.github_repo or "",
            email_from=args.email_from or "",
            email_identity_type=args.email_identity_type or "",
            email_hosted_zone_id=args.email_hosted_zone_id or "",
            enable_staging=bool(args.enable_staging),
        )
        return data, f"wrote {data['wrote']}\nnext: {data['next']}"
    if sub == "synth":
        data = system_cmd.synth(workspace, dry_run=dry)
        return data, data.get("command") or "synth ok"
    if sub == "cdk-bootstrap":
        data = system_cmd.cdk_bootstrap(workspace, profile=profile, region=region, dry_run=dry)
        return data, f"bootstrap {data.get('target')}\nnext: {data.get('next')}"
    if sub == "destroy":
        data = system_cmd.destroy(
            workspace, profile=profile, region=region, yes=bool(args.yes), dry_run=dry
        )
        return data, "destroyed " + ", ".join(data.get("order") or [])
    if sub == "install":
        inst = getattr(args, "system_install_cmd", None)
        if not inst or inst == "help":
            return _noun_help("system")
        if inst == "start":
            data = system_cmd.install_start(workspace, profile=args.profile or profile, region=region)
            return data, f"system install started env={data['sheet']['env']}\nnext: {data['next']}"
        if inst == "plan":
            data = system_cmd.install_plan(workspace)
            remaining = ", ".join(data.get("remaining") or []) or "(none)"
            return data, f"remaining: {remaining}\nnext: {data['next']}"
        if inst == "apply":
            data = system_cmd.install_apply(
                workspace,
                through=args.through or "write-state",
                dry_run=dry,
                profile=profile,
                region=region,
            )
            return data, f"ran: {', '.join(data.get('ran') or []) or '(none)'}\nnext: {data['next']}"
    raise RengloError(f"unknown system command: {sub}")


def _stack(workspace: Path, args, profile: str, region: str) -> tuple[dict, str]:
    sub = getattr(args, "stack_cmd", None)
    if not sub or sub == "help":
        return _noun_help("stack")
    dry = bool(getattr(args, "dry_run", False))
    if sub == "status":
        which = getattr(args, "which", "") or ""
        data = stack_cmd.status(workspace, which, profile=profile, region=region)
        return data, _format_stack_status_text(data)
    if sub == "deploy":
        oidc = None
        if getattr(args, "create_github_oidc", False):
            oidc = True
        data = stack_cmd.deploy(
            workspace,
            stacks=stack_cmd.parse_stacks(args.stack),
            profile=profile,
            region=region,
            create_github_oidc=oidc,
            write_state=bool(args.write_state),
            dry_run=dry,
        )
        cmds = "\n".join(f"  {c}" for c in data.get("commands") or [])
        prefix = "dry-run:\n" if data.get("dry_run") else "deployed:\n"
        return data, f"{prefix}{cmds}\nnext: {data['next']}"
    if sub == "destroy":
        data = stack_cmd.destroy(
            workspace,
            stacks=stack_cmd.parse_stacks(args.stack),
            profile=profile,
            region=region,
            yes=bool(args.yes),
            dry_run=dry,
        )
        return data, "destroy " + ", ".join(data.get("order") or [])
    raise RengloError(f"unknown stack command: {sub}")


def _state(workspace: Path, args, profile: str, region: str) -> tuple[dict, str]:
    sub = getattr(args, "state_cmd", None)
    if not sub or sub == "help":
        return _noun_help("state")
    dry = bool(getattr(args, "dry_run", False))
    if sub == "show":
        data = state_cmd.show(workspace, profile=profile, region=region)
        return data, state_cmd.format_state_show_text(data)
    if sub == "write":
        data = state_cmd.write(workspace, profile=profile, region=region, dry_run=dry)
        return data, data.get("command") or "write-state ok"
    if sub == "local-config":
        data = state_cmd.local_config(workspace, profile=profile, region=region, dry_run=dry)
        return data, f"wrote {data.get('output')}"
    raise RengloError(f"unknown state command: {sub}")


def _email(workspace: Path, args, profile: str, region: str) -> tuple[dict, str]:
    sub = getattr(args, "email_cmd", None)
    if not sub or sub == "help":
        return _noun_help("email")
    dry = bool(getattr(args, "dry_run", False))
    if sub == "sender-status":
        data = emailcmd.sender_status(workspace, profile=profile, region=region)
        ver = (data.get("verification") or {}).get("status")
        return data, (
            f"from: {data.get('from_email')}  mode: {data.get('SesDnsMode')}  "
            f"verification: {ver}  sandbox: {data.get('sandbox')}\nnext: {data.get('next')}"
        )
    if sub == "verify-sender":
        data = emailcmd.verify_sender(workspace, profile=profile, region=region, dry_run=dry)
        return data, f"sender {data.get('from_email')} {data.get('verification')}\nnext: {data.get('next')}"
    if sub == "allow":
        data = emailcmd.allow(workspace, args.address, profile=profile, region=region, dry_run=dry)
        return data, f"allowed {data.get('address')}\nnext: {data.get('next')}"
    if sub == "allow-status":
        data = emailcmd.allow_status(workspace, profile=profile, region=region)
        lines = [
            f"sandbox: {data.get('sandbox')}",
        ]
        rows = data.get("identities") or []
        if not rows:
            lines.append("  (no SES identities)")
        for row in rows:
            lines.append(f"  {row['identity']:40} {row['type']:7} {row['status']}")
        if data.get("hint"):
            lines.append(data["hint"])
        return data, "\n".join(lines)
    raise RengloError(f"unknown email command: {sub}")


def _admin(workspace: Path, args, profile: str, region: str) -> tuple[dict, str]:
    sub = getattr(args, "admin_cmd", None)
    if not sub or sub == "help":
        return _noun_help("admin")
    dry = bool(getattr(args, "dry_run", False))
    if sub == "create":
        data = admin_cmd.create(
            workspace,
            args.email,
            profile=profile,
            region=region,
            console=getattr(args, "console", "") or "",
            dry_run=dry,
        )
        verb = str(data.get("action") or "created")
        return data, (
            f"{verb} {data['email']} (console={data['console']})\n"
            f"setup: {data['setup_url']}\n"
            f"local: {data['local_setup_url']}\n"
            f"hint: {data.get('hint')}\nnext: {data['next']}"
        )
    if sub == "show":
        data = admin_cmd.show(workspace, args.email, profile=profile, region=region)
        if not data.get("exists"):
            return data, f"{data['email']}: not in pool {data['user_pool_id']}"
        return data, f"{data['email']}: {data.get('status')} enabled={data.get('enabled')}"
    raise RengloError(f"unknown admin command: {sub}")


def _user(workspace: Path, args, profile: str, region: str) -> tuple[dict, str]:
    sub = getattr(args, "user_cmd", None)
    if not sub or sub == "help":
        return _noun_help("user")
    if sub == "invite":
        data = user_cmd.invite(
            workspace,
            args.email,
            team=args.team or "",
            portfolio=args.portfolio or "",
            api_url=args.api_url or "",
            token=args.token or "",
            admin_email=args.admin_email or "",
            admin_password=args.admin_password or "",
            profile=profile,
            region=region,
            dry_run=bool(getattr(args, "dry_run", False)),
        )
        return data, f"invite {data.get('email')} via {data.get('url')}"
    raise RengloError(f"unknown user command: {sub}")


def _extension(workspace: Path, args) -> tuple[dict, str]:
    sub = getattr(args, "extension_cmd", None)
    if not sub or sub == "help":
        return _noun_help("extension")
    if sub == "status":
        data = ext_cmd.status(workspace)
        return data, _ext_status_text(data)
    if sub == "show":
        data = ext_cmd.show_handle(workspace, args.handle)
        owners = ", ".join(data.get("owners") or []) or "(not in catalog)"
        return data, (
            f"handle:    {data['handle']}\n"
            f"python:    {data['python']}\n"
            f"owners:    {owners}\n"
            f"role:      {data['role']}\n"
            f"installer: {data['installer']}\n"
            f"env:       {data['env']}"
        )
    if sub == "tree":
        data = ext_cmd.tree(workspace)
        rows = data.get("extensions") or []
        if not rows:
            return data, f"{data['env']}: no catalog extensions"
        lines = [f"{data['env']}"]
        for row in rows:
            lines.append(f"  {row['handle']:20} {row['owner']:16} {row['python']}")
        return data, "\n".join(lines)
    if sub == "install":
        return _extension_install(workspace, args)
    raise RengloError(f"unknown extension command: {sub}")


def _extension_install(workspace: Path, args) -> tuple[dict, str]:
    inst = getattr(args, "extension_install_cmd", None)
    if not inst or inst == "help":
        return _noun_help("extension")
    if inst == "place":
        data = ext_cmd.place(
            workspace,
            args.handle,
            hub=bool(args.hub),
            peer=args.peer or "",
            new_peer=args.new_peer or "",
            compute=args.compute or "fargate",
            task_size=args.task_size or "medium",
            python_version=args.python_version or "",
            npm=args.npm or "",
            aws_profile=args.profile or "",
            aws_region=args.region or "",
        )
        return data, (
            f"placed {data['sheet']['handle']} on {data['sheet']['path']} "
            f"{data['sheet'].get('peer_id') or ''} "
            f"(profile {data['sheet']['aws_profile']})\nnext: {data['next']}"
        )
    if inst == "plan":
        data = ext_cmd.plan(workspace)
        cfg = data["config"]
        lines = [
            f"handle:  {data['sheet']['handle']}",
            f"config:  {cfg['file']}  packages.{cfg['packages']}  {cfg['placement']}",
            f"pin:     {data['pin']}",
            f"publish: {data['publish']}",
            "deploy:",
        ]
        for cmd in data.get("deploy_commands") or []:
            lines.append(f"  {cmd}")
        lines.append(f"push:    {data['push']}")
        lines.append("skip:    " + ", ".join(data["skip"]))
        lines.append(f"next:    {data['next']}")
        return data, "\n".join(lines)
    if inst == "config":
        data = ext_cmd.config(workspace)
        return data, f"wrote {data['wrote']}\nnext: {data['next']}"
    if inst == "pin":
        data = ext_cmd.pin(workspace, args.python_version or "", args.npm_version or "")
        pin = data["pin"]
        return data, f"pin {pin['from']} → {pin['to']} ({pin['pin']})\nnext: {data['next']}"
    if inst == "publish":
        data = ext_cmd.publish(workspace, skip_upload=bool(args.skip_upload))
        extra = " (not uploaded)" if not data.get("uploaded") else ""
        return data, f"wheel {data['wheel']}{extra}\nnext: {data['next']}"
    if inst == "deploy":
        data = ext_cmd.deploy(workspace, dry_run=bool(args.dry_run))
        cmds = "\n".join(f"  {c}" for c in data.get("commands") or [])
        prefix = "dry-run:\n" if data.get("dry_run") else "deployed:\n"
        return data, f"{prefix}{cmds}\nnext: {data['next']}"
    if inst == "test":
        data = ext_cmd.test(workspace, skip_synth=bool(args.skip_synth))
        return data, f"test ok ({data['checks']['unique_owner']})\nnext: {data['next']}"
    if inst == "push":
        data = ext_cmd.push(workspace, yes=bool(args.yes), no_push=bool(args.no_push))
        return data, f"BOM {data['git']['commit']} pushed={data['git']['pushed']}\nnext: {data['next']}"
    if inst == "finish":
        data = ext_cmd.finish(workspace)
        return data, (
            f"{data['handle']} role=product. {data['convoy']}\n"
            f"sheet {data['sheet']}. {data['next']}"
        )
    raise RengloError(f"unknown extension install command: {inst}")


def _peer(workspace: Path, args, profile: str, region: str) -> tuple[dict, str]:
    sub = getattr(args, "peer_cmd", None)
    if not sub or sub == "help":
        return _noun_help("peer")
    dry = bool(getattr(args, "dry_run", False))
    if sub == "list":
        data = peer_cmd.list_peers(workspace)
        lines = [data["env"]]
        for row in data.get("peers") or []:
            lines.append(
                f"  {row['id']:16} {row.get('compute', ''):12} {', '.join(row.get('extensions') or [])}"
            )
        return data, "\n".join(lines)
    if sub == "show":
        data = peer_cmd.show(workspace, args.peer_id)
        peer = data["peer"]
        return data, (
            f"{peer['id']} compute={peer.get('compute')} "
            f"extensions={peer.get('extensions')} peers_bom={peer.get('peers_bom')}"
        )
    if sub == "status":
        data = peer_cmd.status(
            workspace,
            profile=profile,
            region=region,
            peer_id=getattr(args, "peer_id", "") or "",
        )
        return data, _format_peer_status_text(data)
    if sub == "synth":
        data = peer_cmd.synth(workspace, args.peer_id, profile=profile, dry_run=dry)
        return data, data.get("command") or f"synth {args.peer_id}"
    if sub == "deploy":
        data = peer_cmd.deploy(
            workspace,
            args.peer_id,
            profile=profile,
            region=region,
            write_state=bool(args.write_state),
            dry_run=dry,
        )
        return data, (data.get("command") or f"deploy {args.peer_id}") + f"\nnext: {data.get('next')}"
    if sub == "destroy":
        data = peer_cmd.destroy(
            workspace, args.peer_id, profile=profile, yes=bool(args.yes), dry_run=dry
        )
        return data, data.get("command") or f"destroy {args.peer_id}"
    raise RengloError(f"unknown peer command: {sub}")


def _format_peer_status_text(data: dict) -> str:
    lines = [data["env"]]
    for row in data.get("peers") or []:
        lines.append(f"  {row['id']:16} {row['name']} {row['status']}")
    if len(lines) == 1:
        lines.append("  (no peers in deploy_targets.yml)")
    return "\n".join(lines)


def _format_stack_status_text(data: dict) -> str:
    lines = [data["env"]]
    for letter, row in (data.get("stacks") or {}).items():
        lines.append(f"  {letter}: {row['name']} {row['status']}")
    for row in data.get("peers") or []:
        lines.append(f"  {row['id']}: {row['name']} {row['status']}")
    return "\n".join(lines)


def _status_text(data: dict) -> str:
    lines = [
        f"env:      {data.get('env')}",
        f"stacks:   a={((data.get('stacks') or {}).get('a'))}  b={((data.get('stacks') or {}).get('b'))}",
    ]
    peer_rows = data.get("peers") or []
    if peer_rows:
        peer_bits = "  ".join(f"{row['id']}={row['status']}" for row in peer_rows)
        lines.append(f"peers:    {peer_bits}")
    ssm = data.get("ssm") or {}
    if ssm:
        lines.append(f"ssm:      FROM_EMAIL={ssm.get('FROM_EMAIL')} BASE_URL={ssm.get('BASE_URL')}")
    if data.get("extension"):
        ext = data["extension"]
        lines.append(f"incubating: {ext.get('handle')} {ext.get('phase')}")
    if data.get("system"):
        sys_s = data["system"]
        lines.append(f"system:   phase={sys_s.get('phase')} done={sys_s.get('done')}")
    lines.append(f"next:     {data.get('next')}")
    return "\n".join(lines)


def _doctor_text(data: dict) -> str:
    lines = [f"workspace {data.get('layout')}: {data.get('workspace')}"]
    for check in data.get("checks") or []:
        mark = "ok" if check.get("ok") else "FAIL"
        lines.append(f"  {check['name']:16} {mark}  {check.get('detail')}")
    return "\n".join(lines)


def _ext_status_text(data: dict) -> str:
    if not data.get("incubating"):
        return f"{data['hint']}\nnext: {data['next']}"
    sheet = data["sheet"]
    return (
        f"handle:   {sheet.get('handle')}\n"
        f"path:     {sheet.get('path')} {sheet.get('peer_id') or ''}\n"
        f"profile:  {sheet.get('aws_profile') or '(missing)'}\n"
        f"region:   {sheet.get('aws_region') or '(from config)'}\n"
        f"phase:    {sheet.get('phase')}\n"
        f"test:     {sheet.get('test') or 'not run'}\n"
        f"next:     {data['next']}"
    )


def invoked_prog() -> str:
    name = Path(sys.argv[0]).name.lower()
    if name.endswith(".exe"):
        name = name[:-4]
    if name == "arbitium":
        return "arbitium"
    return "renglo"


def _aws_flags(parser: argparse.ArgumentParser) -> None:
    """Accept --profile/--region after the verb. Parent flags only work before it."""
    parser.add_argument("--profile", default=argparse.SUPPRESS, help="AWS CLI profile")
    parser.add_argument("--region", default=argparse.SUPPRESS, help="AWS region")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=invoked_prog(),
        description="Operator CLI above bootstrap, launcher, and bom-helper.",
    )
    parser.add_argument("--json", action="store_true", help="JSON output")
    parser.add_argument("--workspace", default=None, help="Workspace root")
    parser.add_argument("--profile", default="", help="AWS CLI profile")
    parser.add_argument("--region", default="", help="AWS region")
    sub = parser.add_subparsers(dest="cmd")

    p_help = sub.add_parser("help", help="List commands")
    p_help.add_argument("topic", nargs="?", default="")

    p_status = sub.add_parser("status", help="Env, stacks, SSM, sheets, next command")
    _aws_flags(p_status)
    p_doctor = sub.add_parser("doctor", help="Local toolchain and workspace checks")
    _aws_flags(p_doctor)

    system = sub.add_parser("system", help="New tenant / platform config")
    ssub = system.add_subparsers(dest="system_cmd")
    ssub.add_parser("help")
    p_init = ssub.add_parser("init", help="Write customer-config.json")
    p_init.add_argument("--env-name", required=True)
    p_init.add_argument("--github-repo", required=True)
    p_init.add_argument("--email-from", required=True)
    p_init.add_argument("--email-identity-type", required=True, choices=["domain", "email"])
    p_init.add_argument("--email-hosted-zone-id", default="")
    p_init.add_argument("--enable-staging", action="store_true")
    p_synth = ssub.add_parser("synth")
    p_synth.add_argument("--dry-run", action="store_true")
    p_boot = ssub.add_parser("cdk-bootstrap")
    _aws_flags(p_boot)
    p_boot.add_argument("--dry-run", action="store_true")
    p_sdest = ssub.add_parser("destroy")
    _aws_flags(p_sdest)
    p_sdest.add_argument("--yes", action="store_true")
    p_sdest.add_argument("--dry-run", action="store_true")
    inst = ssub.add_parser("install")
    isub = inst.add_subparsers(dest="system_install_cmd")
    isub.add_parser("help")
    p_start = isub.add_parser("start")
    p_start.add_argument("--profile", required=True)
    isub.add_parser("plan")
    p_apply = isub.add_parser("apply")
    _aws_flags(p_apply)
    p_apply.add_argument("--through", default="write-state")
    p_apply.add_argument("--dry-run", action="store_true")

    stack = sub.add_parser("stack", help="Stack A/B deploy")
    ksub = stack.add_subparsers(dest="stack_cmd")
    ksub.add_parser("help")
    p_ks = ksub.add_parser("status")
    _aws_flags(p_ks)
    p_ks.add_argument("which", nargs="?", default="")
    p_kd = ksub.add_parser("deploy")
    _aws_flags(p_kd)
    p_kd.add_argument("--stack", required=True, help="a, b, or a,b")
    p_kd.add_argument("--create-github-oidc", action="store_true")
    p_kd.add_argument("--write-state", action="store_true")
    p_kd.add_argument("--dry-run", action="store_true")
    p_kx = ksub.add_parser("destroy")
    _aws_flags(p_kx)
    p_kx.add_argument("--stack", required=True)
    p_kx.add_argument("--yes", action="store_true")
    p_kx.add_argument("--dry-run", action="store_true")

    state = sub.add_parser("state", help="SSM variables")
    tsub = state.add_subparsers(dest="state_cmd")
    tsub.add_parser("help")
    p_tsh = tsub.add_parser("show")
    _aws_flags(p_tsh)
    p_tw = tsub.add_parser("write")
    _aws_flags(p_tw)
    p_tw.add_argument("--dry-run", action="store_true")
    p_tl = tsub.add_parser("local-config")
    _aws_flags(p_tl)
    p_tl.add_argument("--dry-run", action="store_true")

    email = sub.add_parser("email", help="SES")
    esub = email.add_subparsers(dest="email_cmd")
    esub.add_parser("help")
    p_ess = esub.add_parser("sender-status")
    _aws_flags(p_ess)
    p_eas = esub.add_parser("allow-status")
    _aws_flags(p_eas)
    p_ev = esub.add_parser("verify-sender")
    _aws_flags(p_ev)
    p_ev.add_argument("--dry-run", action="store_true")
    p_ea = esub.add_parser("allow")
    _aws_flags(p_ea)
    p_ea.add_argument("address")
    p_ea.add_argument("--dry-run", action="store_true")

    admin = sub.add_parser("admin", help="Cognito admin users")
    asub = admin.add_subparsers(dest="admin_cmd")
    asub.add_parser("help")
    p_ac = asub.add_parser("create")
    _aws_flags(p_ac)
    p_ac.add_argument("email")
    p_ac.add_argument(
        "--console",
        choices=("local", "staging", "production"),
        default="",
        help="invite link base: local (127.0.0.1:5174), staging, or production console URL",
    )
    p_ac.add_argument("--dry-run", action="store_true")
    p_ash = asub.add_parser("show")
    _aws_flags(p_ash)
    p_ash.add_argument("email")

    user = sub.add_parser("user", help="Collaborator invite")
    usub = user.add_subparsers(dest="user_cmd")
    usub.add_parser("help")
    p_ui = usub.add_parser("invite")
    _aws_flags(p_ui)
    p_ui.add_argument("email")
    p_ui.add_argument("--team", required=True)
    p_ui.add_argument("--portfolio", required=True)
    p_ui.add_argument("--api-url", default="")
    p_ui.add_argument("--token", default="")
    p_ui.add_argument("--admin-email", default="")
    p_ui.add_argument("--admin-password", default="")
    p_ui.add_argument("--dry-run", action="store_true")

    ext = sub.add_parser("extension", help="Incubating extension install")
    xsub = ext.add_subparsers(dest="extension_cmd")
    xsub.add_parser("help")
    xsub.add_parser("status")
    p_xsh = xsub.add_parser("show")
    p_xsh.add_argument("handle")
    xsub.add_parser("tree")
    xinst = xsub.add_parser("install")
    xis = xinst.add_subparsers(dest="extension_install_cmd")
    xis.add_parser("help")
    p_place = xis.add_parser("place")
    p_place.add_argument("handle")
    p_place.add_argument("--hub", action="store_true")
    p_place.add_argument("--peer", default="")
    p_place.add_argument("--new-peer", default="")
    p_place.add_argument("--compute", default="fargate")
    p_place.add_argument("--task-size", default="medium")
    p_place.add_argument("--python-version", default="")
    p_place.add_argument("--npm", default="")
    p_place.add_argument("--profile", required=True)
    p_place.add_argument("--region", default="")
    xis.add_parser("plan")
    xis.add_parser("config")
    p_pin = xis.add_parser("pin")
    p_pin.add_argument("--python-version", default="")
    p_pin.add_argument("--npm-version", default="")
    p_pub = xis.add_parser("publish")
    p_pub.add_argument("--skip-upload", action="store_true")
    p_dep = xis.add_parser("deploy")
    p_dep.add_argument("--dry-run", action="store_true")
    p_test = xis.add_parser("test")
    p_test.add_argument("--skip-synth", action="store_true")
    p_push = xis.add_parser("push")
    p_push.add_argument("--yes", action="store_true")
    p_push.add_argument("--no-push", action="store_true")
    xis.add_parser("finish")

    peer = sub.add_parser("peer", help="Peer CDK wrapper")
    psub = peer.add_subparsers(dest="peer_cmd")
    psub.add_parser("help")
    psub.add_parser("list")
    p_pst = psub.add_parser("status")
    _aws_flags(p_pst)
    p_pst.add_argument("--peer-id", default="", help="Optional peer id (default: every catalog peer)")
    p_psh = psub.add_parser("show")
    p_psh.add_argument("peer_id")
    p_psy = psub.add_parser("synth")
    _aws_flags(p_psy)
    p_psy.add_argument("--peer-id", required=True)
    p_psy.add_argument("--dry-run", action="store_true")
    p_pd = psub.add_parser("deploy")
    _aws_flags(p_pd)
    p_pd.add_argument("--peer-id", required=True)
    p_pd.add_argument("--write-state", action="store_true")
    p_pd.add_argument("--dry-run", action="store_true")
    p_px = psub.add_parser("destroy")
    _aws_flags(p_px)
    p_px.add_argument("--peer-id", required=True)
    p_px.add_argument("--yes", action="store_true")
    p_px.add_argument("--dry-run", action="store_true")

    return parser


if __name__ == "__main__":
    raise SystemExit(main())
