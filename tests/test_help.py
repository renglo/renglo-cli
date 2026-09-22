import sys

from renglo_cli.cli import invoked_prog, main
from renglo_cli.help_text import format_help_text, help_payload


def test_help_exit_zero() -> None:
    assert main(["help"]) == 0
    assert main(["help", "system"]) == 0
    assert main(["help", "extension"]) == 0
    assert main(["system", "help"]) == 0
    assert main(["extension", "install", "help"]) == 0


def test_help_lists_nouns() -> None:
    text = format_help_text()
    assert "renglo status" in text
    assert "renglo stack deploy" in text
    assert "renglo extension install place" in text
    assert "Not git-convoy" in text
    payload = help_payload("stack")
    assert any("stack deploy" in c for c in payload["commands"])


def test_arbitium_is_the_same_entry(monkeypatch) -> None:
    monkeypatch.setattr(sys, "argv", ["arbitium"])
    assert invoked_prog() == "arbitium"
    assert main(["help"]) == 0
