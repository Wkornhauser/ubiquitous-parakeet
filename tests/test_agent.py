"""Tests for agent.py.

Uses an in-file fake Anthropic client to keep tests fast, deterministic, and
free of API calls.
"""
import pytest

import agent


class FakeBlock:
    """Minimal stand-in for an anthropic content block."""
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)


class FakeResponse:
    def __init__(self, content):
        self.content = content


class FakeMessages:
    def __init__(self, response):
        self._response = response
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self._response


class FakeClient:
    def __init__(self, response):
        self.messages = FakeMessages(response)


def make_tool_use_response(category="billing", urgency="high", summary="Test summary."):
    return FakeResponse([
        FakeBlock(
            type="tool_use",
            id="toolu_test",
            name="submit_triage",
            input={"category": category, "urgency": urgency, "summary": summary},
        )
    ])


def make_text_response(text="hello"):
    return FakeResponse([FakeBlock(type="text", text=text)])


# ---------------------------------------------------------------------------
# triage()
# ---------------------------------------------------------------------------

def test_triage_returns_tool_input():
    client = FakeClient(make_tool_use_response(
        category="billing", urgency="high", summary="Customer charged twice."
    ))
    result = agent.triage("I was charged twice", client)
    assert result == {
        "category": "billing",
        "urgency": "high",
        "summary": "Customer charged twice.",
    }


def test_triage_raises_when_no_tool_use():
    client = FakeClient(make_text_response("I refuse to classify"))
    with pytest.raises(RuntimeError):
        agent.triage("something", client)


def test_triage_forces_tool_use():
    client = FakeClient(make_tool_use_response())
    agent.triage("ticket", client)
    assert len(client.messages.calls) == 1
    call = client.messages.calls[0]
    assert call["tool_choice"] == {"type": "tool", "name": "submit_triage"}
    tool_names = [t["name"] for t in call["tools"]]
    assert "submit_triage" in tool_names


# ---------------------------------------------------------------------------
# route()
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("category", ["billing", "technical", "general"])
def test_route_dispatches_by_category(monkeypatch, category):
    calls = []

    def fake_handler(ticket, triage_result, client):
        calls.append((category, ticket, triage_result))
        return f"handled by {category}"

    monkeypatch.setitem(agent.HANDLERS, category, fake_handler)
    triage_result = {"category": category, "urgency": "low", "summary": "s"}
    out = agent.route("ticket text", triage_result, client=object())
    assert out == f"handled by {category}"
    assert calls == [(category, "ticket text", triage_result)]


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("handler_name, expected_system_prompt", [
    ("handle_billing", "BILLING_SYSTEM_PROMPT"),
    ("handle_technical", "TECHNICAL_SYSTEM_PROMPT"),
    ("handle_general", "GENERAL_SYSTEM_PROMPT"),
])
def test_handler_uses_category_system_prompt(handler_name, expected_system_prompt):
    client = FakeClient(make_text_response("resolution body"))
    handler = getattr(agent, handler_name)
    triage_result = {"category": "billing", "urgency": "high", "summary": "Summary line."}
    handler("the original ticket", triage_result, client)

    assert len(client.messages.calls) == 1
    call = client.messages.calls[0]
    expected = getattr(agent, expected_system_prompt)
    assert call["system"] == expected
    user_blob = str(call["messages"])
    assert "the original ticket" in user_blob
    assert "Summary line." in user_blob


def test_handler_returns_response_text():
    client = FakeClient(make_text_response("Here is your resolution."))
    triage_result = {"category": "billing", "urgency": "low", "summary": "s"}
    out = agent.handle_billing("ticket", triage_result, client)
    assert out == "Here is your resolution."
