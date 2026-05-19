"""Customer support triage agent — classifier, handlers, and dispatcher."""
from typing import Callable

MODEL = "claude-opus-4-7"
MAX_TOKENS_TRIAGE = 1024
MAX_TOKENS_HANDLER = 4096


TRIAGE_TOOL = {
    "name": "submit_triage",
    "description": "Submit the triage classification for a support ticket.",
    "input_schema": {
        "type": "object",
        "properties": {
            "category": {
                "type": "string",
                "enum": ["billing", "technical", "general"],
                "description": (
                    "billing: charges, refunds, invoices, payment methods. "
                    "technical: bugs, errors, outages, integration issues. "
                    "general: how-to questions, account info, feature requests, anything else."
                ),
            },
            "urgency": {
                "type": "string",
                "enum": ["high", "medium", "low"],
                "description": (
                    "high: service down, active payment failure, security issue, customer blocked. "
                    "medium: degraded functionality, time-sensitive but not blocking. "
                    "low: questions, feature requests, informational."
                ),
            },
            "summary": {
                "type": "string",
                "description": "A neutral 1-2 sentence summary of the ticket suitable for a handler queue.",
            },
        },
        "required": ["category", "urgency", "summary"],
    },
}


TRIAGE_SYSTEM_PROMPT = (
    "You are a customer support triage classifier. Read the incoming ticket "
    "and call the submit_triage tool exactly once with the appropriate "
    "category, urgency, and a concise summary. Do not respond with text — "
    "only call the tool."
)

BILLING_SYSTEM_PROMPT = (
    "You are a billing support specialist. The ticket has been triaged as a "
    "billing issue. Acknowledge the customer's concern, explain what you "
    "would check (invoice history, payment method, refund eligibility, "
    "subscription status), and propose a concrete next step. Be empathetic "
    "but professional. Keep the response to 3-5 short paragraphs."
)

TECHNICAL_SYSTEM_PROMPT = (
    "You are a senior technical support engineer. The ticket has been triaged "
    "as a technical issue. Acknowledge the problem, suggest concrete "
    "diagnostic steps (logs to check, configuration to verify, reproduction "
    "steps), and propose either a fix or an escalation path. Keep the "
    "response to 3-5 short paragraphs."
)

GENERAL_SYSTEM_PROMPT = (
    "You are a general customer support agent. The ticket has been triaged "
    "as a general inquiry. Answer the customer's question directly if you "
    "can, or point them to the right resource (docs, account settings, "
    "another team). Keep the response brief — 2-4 short paragraphs."
)


def triage(ticket: str, client) -> dict:
    """Classify a ticket. Returns {category, urgency, summary}."""
    response = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS_TRIAGE,
        system=TRIAGE_SYSTEM_PROMPT,
        tools=[TRIAGE_TOOL],
        tool_choice={"type": "tool", "name": "submit_triage"},
        messages=[{"role": "user", "content": ticket}],
    )
    for block in response.content:
        if getattr(block, "type", None) == "tool_use" and getattr(block, "name", None) == "submit_triage":
            return block.input
    raise RuntimeError(
        f"Triage classifier did not call submit_triage. Response content: {response.content!r}"
    )


def _handle(system_prompt: str, ticket: str, triage_result: dict, client) -> str:
    user_message = (
        f"Triage summary: {triage_result['summary']}\n"
        f"Urgency: {triage_result['urgency']}\n\n"
        f"Original ticket:\n{ticket}"
    )
    response = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS_HANDLER,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
    )
    for block in response.content:
        if getattr(block, "type", None) == "text":
            return block.text
    raise RuntimeError(f"Handler got no text response: {response.content!r}")


def handle_billing(ticket: str, triage_result: dict, client) -> str:
    return _handle(BILLING_SYSTEM_PROMPT, ticket, triage_result, client)


def handle_technical(ticket: str, triage_result: dict, client) -> str:
    return _handle(TECHNICAL_SYSTEM_PROMPT, ticket, triage_result, client)


def handle_general(ticket: str, triage_result: dict, client) -> str:
    return _handle(GENERAL_SYSTEM_PROMPT, ticket, triage_result, client)


HANDLERS: dict[str, Callable[[str, dict, object], str]] = {
    "billing": handle_billing,
    "technical": handle_technical,
    "general": handle_general,
}


def route(ticket: str, triage_result: dict, client) -> str:
    return HANDLERS[triage_result["category"]](ticket, triage_result, client)
