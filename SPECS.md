# Customer Support Triage Agent — Implementation Plan

## Context

Build a CLI tool that accepts a free-text customer support ticket, uses Claude to classify it (category + urgency + summary), then routes the ticket to a category-specific handler that produces a mock resolution. The working directory `C:\Users\Wil\Desktop\Triage-Agent` is currently empty — this is a greenfield project.

The agent demonstrates a two-stage LLM pipeline (classify → dispatch → handler), which is a common pattern for production triage / routing systems. Output should be readable in a terminal and clearly show both the triage decision and the resolution.

## Architecture

**Two-stage flow:**

1. **Triage call** — One Claude API call with a system prompt that instructs Claude to act as a triage classifier. Structured output is forced via a `submit_triage` tool the model is required to call. The tool input schema is the canonical structure: `{category, urgency, summary}`.
2. **Dispatch** — Plain Python `dict` mapping category → handler function. No conditionals, no class hierarchy.
3. **Handler call** — The matching handler function makes a second Claude API call with a category-specific system prompt (billing specialist / technical engineer / general support). It receives the original ticket + the triage summary as context and returns a mock resolution string.

**Why tool-forced structured output (not "respond in JSON" instructions):** The Anthropic SDK's tool-use mechanism guarantees a valid JSON object matching the schema. Free-form "return JSON" prompts can produce markdown fences, prose preambles, or schema drift that require parsing fallbacks.

**Model:** `claude-opus-4-7` for both calls (per Anthropic SDK default guidance — most capable model; user can swap to sonnet/haiku in `agent.py` if they want lower latency/cost).

## File Layout

Single-package layout. Small enough that fragmentation would hurt readability; structured enough that each file has one job.

```
C:\Users\Wil\Desktop\Triage-Agent\
├── triage.py              # CLI entry point: input gathering + output formatting
├── agent.py               # Core: triage() classifier + handler functions + dispatcher
├── tests/
│   ├── test_agent.py      # Unit tests for triage(), route(), handlers
│   └── test_cli.py        # Unit tests for CLI input gathering + error exits
├── requirements.txt       # anthropic
├── requirements-dev.txt   # pytest (dev-only)
├── .env.example           # ANTHROPIC_API_KEY=...
└── .gitignore             # .env, __pycache__, etc.
```

## Component Details

### `agent.py`

- `TRIAGE_TOOL` — tool schema dict with fields:
  - `category`: enum `["billing", "technical", "general"]`
  - `urgency`: enum `["high", "medium", "low"]`
  - `summary`: 1-2 sentence structured summary of the ticket
- `TRIAGE_SYSTEM_PROMPT` — instructs Claude to read a ticket and call the `submit_triage` tool. Includes brief definitions of each category and what makes a ticket high/medium/low urgency (e.g. "high = service down, payment failure on active charge, security; low = feature request, how-to question").
- `triage(ticket: str, client) -> dict` — sends ticket to Claude with `tool_choice={"type": "tool", "name": "submit_triage"}` to force tool use. Extracts the tool_use block from the response and returns its `input` dict.
- Per-category system prompts:
  - `BILLING_SYSTEM_PROMPT` — "You are a billing specialist. Acknowledge the issue, explain what you would check (invoices, payment method, refund eligibility), and offer a next step."
  - `TECHNICAL_SYSTEM_PROMPT` — "You are a senior support engineer. Acknowledge, suggest diagnostic steps, and propose a fix or escalation path."
  - `GENERAL_SYSTEM_PROMPT` — "You are a general support agent. Answer the question or direct the customer to the right resource."
- `handle_billing(ticket, triage_result, client) -> str` and equivalents for technical and general. Each makes one Claude call with the category-specific system prompt; the user message includes both the original ticket and the triage summary. Returns the model's text content as the mock resolution.
- `HANDLERS` — `dict[str, Callable]` mapping `"billing" → handle_billing` etc.
- `route(ticket, triage_result, client) -> str` — `HANDLERS[triage_result["category"]](ticket, triage_result, client)`.

### `triage.py` (CLI)

- Reads ticket text from, in priority order:
  1. `sys.argv[1]` if present
  2. stdin if not a TTY (piped input)
  3. Interactive `input()` prompt with instructions ("paste ticket, then Ctrl-D / Ctrl-Z to finish") for multi-line capture
- Loads `ANTHROPIC_API_KEY` via `os.environ`. If missing, print a clear error mentioning `.env.example` and exit 1.
- Instantiates `anthropic.Anthropic()` once and passes it into `triage()` and `route()`.
- Prints in this format (plain text, no color libraries — keeps the dependency footprint to just `anthropic`):

  ```
  === Triage ===
  Category: billing
  Urgency:  high
  Summary:  Customer charged twice for May subscription; requesting refund.

  === Resolution (billing handler) ===
  <handler text>
  ```

- Wraps Claude calls in a `try/except anthropic.APIError` and prints a friendly error on failure.

## Testing (TDD)

We follow TDD: write each test, watch it fail, write the minimum code to make it pass, then move on. Tests use `pytest` and a small in-file fake `Anthropic` client — no `unittest.mock`, no `responses`/`vcrpy`. The fake's `messages.create()` returns a pre-built response object so tests are fast, deterministic, and free.

**`tests/test_agent.py`:**

- `test_triage_returns_tool_input` — fake client returns a response containing a `tool_use` block with `input = {"category": "billing", "urgency": "high", "summary": "..."}`. `triage(ticket, client)` returns that dict.
- `test_triage_raises_when_no_tool_use` — fake client returns a response with only text content. `triage()` raises a clear `RuntimeError`.
- `test_triage_forces_tool_use` — assert the call to `messages.create` includes `tool_choice={"type": "tool", "name": "submit_triage"}` and the `submit_triage` tool in `tools`.
- `test_route_dispatches_by_category` — parametrized over `("billing", "technical", "general")`. Inject a fake `HANDLERS` dict via monkeypatch; assert the matching handler is called with the ticket and triage result.
- `test_handler_uses_category_system_prompt` — parametrized over handlers. Fake client records the `system` kwarg; assert it matches the expected category-specific prompt and the user message contains the ticket text and the triage summary.
- `test_handler_returns_response_text` — fake client returns a response with a text block; handler returns that text.

**`tests/test_cli.py`:**

CLI is structured so the testable surface is a pure function `get_ticket(argv, stdin, isatty) -> str` and a `main(argv, stdin, isatty, env, client_factory) -> int` that returns an exit code. This avoids `sys.exit`, real `sys.stdin`, real `os.environ`, and real API clients in tests.

- `test_get_ticket_prefers_argv` — when `argv[1]` is provided, returns it regardless of stdin.
- `test_get_ticket_reads_stdin_when_piped` — when no argv and `isatty` is False, returns stdin content.
- `test_get_ticket_uses_interactive_when_tty` — when no argv and `isatty` is True, reads from the provided stdin (simulating interactive paste).
- `test_main_errors_on_empty_ticket` — empty input → exit code 1, error message printed.
- `test_main_errors_on_missing_api_key` — env lacks `ANTHROPIC_API_KEY` → exit code 1, error message mentions `.env.example`.
- `test_main_happy_path` — valid env + ticket + fake client → exit code 0, output contains both `=== Triage ===` and `=== Resolution` headers.

**Running tests:**

```
pip install -r requirements-dev.txt
pytest
pytest tests/test_agent.py::test_triage_returns_tool_input   # single test
```

Tests do NOT call the real Anthropic API and do NOT require `ANTHROPIC_API_KEY`.

## Error Handling

- **Missing API key** → exit 1 with message pointing at `.env.example`.
- **Empty ticket input** → exit 1 with message asking for non-empty input.
- **Triage tool not called** (extremely unlikely with forced `tool_choice`, but defensive) → exit 1 with the model's raw response printed for debugging.
- **API errors** (rate limit, network) → print the error message, exit 1. No retries — this is a one-shot CLI; the user can re-run.

## Verification

After implementation, verify by running each of these and confirming the printed category/urgency/handler matches the obvious-correct answer:

1. **Billing, high urgency:** `python triage.py "I was charged $200 twice today and my card is now overdrawn. This needs to be refunded immediately."`
2. **Technical, high urgency:** `python triage.py "Our entire production deployment is returning 500 errors since 2pm. None of our customers can log in."`
3. **General, low urgency:** `python triage.py "Where can I find documentation for your API?"`
4. **Piped input:** `echo "How do I change my email address?" | python triage.py` — should classify as general/low.
5. **Multi-line interactive:** `python triage.py` with no args, paste a multi-line ticket, Ctrl-Z (Windows) to submit.
6. **Missing API key:** unset `ANTHROPIC_API_KEY`, run script — should exit 1 with a clear message.

Each invocation should print both a `=== Triage ===` block and a `=== Resolution (... handler) ===` block. The handler's resolution should reference the ticket content (not generic boilerplate) — that's the signal Claude is genuinely conditioning on the ticket and triage summary.

## What's Out of Scope

- No integration tests against the live Anthropic API. Tests use a fake client; live-API tests would be flaky and expensive.
- No logging framework. `print()` is sufficient for a CLI.
- No retry/backoff. One-shot CLI; user can re-run.
- No `colorama` / `rich`. Plain text output keeps the runtime dep footprint to just `anthropic`.
- No README.md (per repo instructions: don't create docs unless asked).
