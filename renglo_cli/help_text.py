from __future__ import annotations

from typing import TypedDict


class HelpSection(TypedDict):
    name: str
    commands: list[str]


HELP_SECTIONS: list[HelpSection] = [
    {
        "name": "Any time",
        "commands": [
            "renglo help [topic]",
            "renglo status",
            "renglo doctor",
        ],
    },
    {
        "name": "system — new tenant / platform config",
        "commands": [
            "renglo system init --env-name NAME --github-repo ORG/BOM --email-from ADDR --email-identity-type domain|email",
            "renglo system synth",
            "renglo system cdk-bootstrap",
            "renglo system destroy [--yes]",
            "renglo system install start --profile PROFILE",
            "renglo system install plan",
            "renglo system install apply [--through write-state]",
        ],
    },
    {
        "name": "stack — day-2 A/B deploy",
        "commands": [
            "renglo stack status [a|b]",
            "renglo stack deploy --stack a|b|a,b [--create-github-oidc] [--write-state] [--dry-run]",
            "renglo stack destroy --stack a|b|a,b [--yes]",
        ],
    },
    {
        "name": "state — SSM variables",
        "commands": [
            "renglo state show",
            "renglo state write [--dry-run]",
            "renglo state local-config",
        ],
    },
    {
        "name": "email — SES",
        "commands": [
            "renglo email sender-status",
            "renglo email allow-status",
            "renglo email verify-sender",
            "renglo email allow ADDRESS",
        ],
    },
    {
        "name": "admin — Cognito",
        "commands": [
            "renglo admin create EMAIL",
            "renglo admin show EMAIL",
        ],
    },
    {
        "name": "user — collaborators (running API)",
        "commands": [
            "renglo user invite EMAIL --team TEAM --portfolio PORTFOLIO [--api-url URL] [--token TOKEN | --admin-email E --admin-password P]",
        ],
    },
    {
        "name": "extension — incubating install",
        "commands": [
            "renglo extension status",
            "renglo extension show HANDLE",
            "renglo extension tree",
            "renglo extension install place HANDLE --hub|--peer PEER|--new-peer PEER --profile PROFILE",
            "renglo extension install plan",
            "renglo extension install config",
            "renglo extension install pin [--python-version X.Y.Z]",
            "renglo extension install publish [--skip-upload]",
            "renglo extension install deploy [--dry-run]",
            "renglo extension install test [--skip-synth]",
            "renglo extension install push [--yes]",
            "renglo extension install finish",
        ],
    },
    {
        "name": "peer — bom-helper CDK wrapper",
        "commands": [
            "renglo peer list",
            "renglo peer status [--peer-id PEER]",
            "renglo peer show PEER",
            "renglo peer synth --peer-id PEER",
            "renglo peer deploy --peer-id PEER [--write-state] [--dry-run]",
            "renglo peer destroy --peer-id PEER [--yes]",
        ],
    },
]


COMMAND_BLURBS: dict[str, str] = {
    "help": "List nouns and verbs.",
    "status": "Env, stacks, SSM, SES, sheets, and the next command.",
    "doctor": "Python 3.12, CDK, bootstrap venv, AWS identity, workspace layout.",
    "init": "Write customer-config.json. Does not set extension_path.",
    "synth": "bootstrap/install.py synth.",
    "cdk-bootstrap": "cdk bootstrap once per account/region.",
    "destroy": "Tear down stacks (B then A).",
    "start": "Open a system install sheet.",
    "plan": "Print remaining phases without writing.",
    "apply": "Run remaining infra phases; stops before SES/admin.",
    "deploy": "Deploy stack A and/or B. Stack A is never implied.",
    "show": "Inspect current values.",
    "write": "bootstrap/install.py write-state.",
    "local-config": "Generate bootstrap/output/<env>/local-dev/.",
    "verify-sender": "Check or resend SES From-address verification.",
    "sender-status": "From-address, DNS mode, verification, sandbox vs production.",
    "allow-status": "SES identities and verify-email-identity status.",
    "allow": "SES sandbox recipient whitelist.",
    "create": "cognito-idp admin-create-user.",
    "invite": "POST /_auth/user/invite (running API + admin session).",
    "place": "Start an incubation sheet (gitconvoy.toml incubating).",
    "config": "Edit deploy_targets.yml placement only.",
    "pin": "New BOM version file + pointer bump.",
    "publish": "First wheel to CodeArtifact.",
    "test": "Installer + unique owner.",
    "push": "Commit/push *-bom main for this incubation only.",
    "finish": "role=product, git convoy init, clear sheet.",
    "list": "Catalog peers.",
    "status": "CloudFormation status for every catalog peer stack.",
    "tree": "Every catalog handle → hub or peer.",
}


def help_payload(topic: str = "") -> dict:
    topic = (topic or "").strip().lower()
    if topic in COMMAND_BLURBS and topic not in (
        "system",
        "stack",
        "state",
        "email",
        "admin",
        "user",
        "extension",
        "peer",
    ):
        return {"ok": True, "topic": topic, "blurb": COMMAND_BLURBS[topic]}
    if topic:
        section = next(
            (s for s in HELP_SECTIONS if s["name"].split(" —", 1)[0].strip() == topic),
            None,
        )
        if section:
            return {
                "ok": True,
                "topic": topic,
                "commands": section["commands"],
            }
    return {
        "ok": True,
        "topic": topic,
        "sections": HELP_SECTIONS,
        "blurbs": COMMAND_BLURBS,
    }


def format_help_text(topic: str = "") -> str:
    payload = help_payload(topic)
    if payload.get("blurb"):
        return f"{payload['topic']}: {payload['blurb']}"
    lines = [
        "renglo — operator CLI above bootstrap, launcher, and bom-helper",
        "",
        "Not git-convoy. Not publisher. Stack A is never implied.",
        "",
    ]
    sections = payload.get("sections") or HELP_SECTIONS
    if payload.get("commands") and not payload.get("sections"):
        lines.append(payload.get("topic") or "commands")
        for cmd in payload["commands"]:
            lines.append(f"  {cmd}")
        lines.append("")
        return "\n".join(lines).rstrip() + "\n"
    for section in sections:
        if payload.get("topic") and payload["topic"] not in section["name"]:
            continue
        lines.append(section["name"])
        for cmd in section["commands"]:
            lines.append(f"  {cmd}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
