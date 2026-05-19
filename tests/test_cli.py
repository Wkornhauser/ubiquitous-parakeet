"""Tests for triage.py (the CLI)."""
import io

import triage


class FakeBlock:
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)


class FakeResponse:
    def __init__(self, content):
        self.content = content


class TwoCallMessages:
    """Returns triage tool_use on first call, handler text on second."""
    def __init__(self, triage_input, handler_text):
        self._triage_input = triage_input
        self._handler_text = handler_text
        self.calls = 0

    def create(self, **kwargs):
        self.calls += 1
        if self.calls == 1:
            return FakeResponse([
                FakeBlock(
                    type="tool_use",
                    id="toolu_test",
                    name="submit_triage",
                    input=self._triage_input,
                )
            ])
        return FakeResponse([FakeBlock(type="text", text=self._handler_text)])


class FakeClient:
    def __init__(self, triage_input, handler_text):
        self.messages = TwoCallMessages(triage_input, handler_text)


def make_client_factory(triage_input, handler_text):
    return lambda: FakeClient(triage_input, handler_text)


# ---------------------------------------------------------------------------
# get_ticket()
# ---------------------------------------------------------------------------

def test_get_ticket_prefers_argv():
    stdin = io.StringIO("stdin contents that should be ignored")
    out = triage.get_ticket(
        argv=["triage.py", "ticket from argv"],
        stdin=stdin,
        isatty=False,
    )
    assert out == "ticket from argv"


def test_get_ticket_reads_stdin_when_piped():
    stdin = io.StringIO("piped ticket text")
    out = triage.get_ticket(
        argv=["triage.py"],
        stdin=stdin,
        isatty=False,
    )
    assert out.strip() == "piped ticket text"


def test_get_ticket_uses_interactive_when_tty():
    stdin = io.StringIO("interactively pasted text")
    out = triage.get_ticket(
        argv=["triage.py"],
        stdin=stdin,
        isatty=True,
    )
    assert out.strip() == "interactively pasted text"


# ---------------------------------------------------------------------------
# main()
# ---------------------------------------------------------------------------

def test_main_errors_on_empty_ticket(capsys):
    code = triage.main(
        argv=["triage.py", "   "],
        stdin=io.StringIO(""),
        isatty=False,
        env={"ANTHROPIC_API_KEY": "test-key"},
        client_factory=make_client_factory({}, ""),
    )
    assert code == 1
    captured = capsys.readouterr()
    assert "empty" in (captured.out + captured.err).lower()


def test_main_errors_on_missing_api_key(capsys):
    code = triage.main(
        argv=["triage.py", "real ticket text"],
        stdin=io.StringIO(""),
        isatty=False,
        env={},
        client_factory=make_client_factory({}, ""),
    )
    assert code == 1
    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert "ANTHROPIC_API_KEY" in combined
    assert ".env.example" in combined


def test_main_happy_path(capsys):
    triage_input = {
        "category": "billing",
        "urgency": "high",
        "summary": "Double charge on May invoice.",
    }
    handler_text = "I'll review your billing history and issue a refund."

    code = triage.main(
        argv=["triage.py", "I was charged twice for May"],
        stdin=io.StringIO(""),
        isatty=False,
        env={"ANTHROPIC_API_KEY": "test-key"},
        client_factory=make_client_factory(triage_input, handler_text),
    )
    captured = capsys.readouterr()
    assert code == 0, captured.out + captured.err
    out = captured.out
    assert "=== Triage ===" in out
    assert "billing" in out
    assert "high" in out
    assert "Double charge on May invoice." in out
    assert "=== Resolution" in out
    assert "billing" in out  # handler label
    assert handler_text in out
