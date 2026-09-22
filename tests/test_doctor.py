from renglo_cli.cli import _parser


def test_doctor_accepts_profile_after_subcommand() -> None:
    args = _parser().parse_args(["doctor", "--profile", "arbitium"])
    assert args.cmd == "doctor"
    assert args.profile == "arbitium"


def test_doctor_accepts_profile_before_subcommand() -> None:
    args = _parser().parse_args(["--profile", "arbitium", "doctor"])
    assert args.cmd == "doctor"
    assert args.profile == "arbitium"


def test_email_accepts_profile_after_verb() -> None:
    args = _parser().parse_args(["email", "sender-status", "--profile", "arbitium"])
    assert args.cmd == "email"
    assert args.email_cmd == "sender-status"
    assert args.profile == "arbitium"
