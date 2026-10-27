"""crew/runners/mail.py over a throwaway vault: a handoff and its reply round-trip."""
import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "pa_mail", Path(__file__).resolve().parents[1] / "crew" / "runners" / "mail.py")
mail = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mail)


@pytest.fixture
def vault(tmp_path):
    root = tmp_path / "wiki" / "agents" / "mail"
    for slug in ("claude-code", "gordon"):
        for box in ("inbox", "archive", "trash"):
            (root / slug / box).mkdir(parents=True)
    (root / "participants.md").write_text(
        "| slug | binding | kind | display | status |\n|---|---|---|---|---|\n"
        "| `claude-code` | x | agent | Claude | active |\n"
        "| `gordon` | x | agent | Gordon | active |\n"
        "| `old` | x | agent | Old | retired |\n", encoding="utf-8")
    return tmp_path


def test_a_handoff_reaches_gordon_and_his_reply_comes_back(vault):
    thread, _ = mail.send(vault, "claude-code", ["gordon"], "Handoff", "Read this.")
    assert [r["thread"] for r in mail.inbox(vault, "gordon")] == [thread]
    mail.reply(vault, thread, "gordon", "Read it.")
    rows = mail.inbox(vault, "claude-code")
    assert rows[0]["last_from"] == "gordon" and rows[0]["messages"] == 2
    msgs = mail.mail_lib.thread_messages(vault, thread)
    assert msgs[1][0]["subject"] == "Re: Handoff" and msgs[1][0]["to"] == ["claude-code"]
    assert mail.mail_lib.verify_chain(vault, thread) == []


def test_an_unknown_or_retired_address_is_refused(vault, capsys):
    for to in ("nobody", "old"):
        assert mail.main(["--vault", str(vault), "send", "--from", "claude-code", "--to", to,
                          "--subject", "x", "--body", "y"]) == 2
    assert not list((vault / "wiki" / "agents" / "mail" / "threads").glob("*")) \
        if (vault / "wiki" / "agents" / "mail" / "threads").exists() else True


def test_the_chat_shell_may_run_mail_without_a_card():
    from crew.runners import pa_session
    assert "python crew/runners/mail.py" in pa_session.READ_ONLY_COMMANDS
