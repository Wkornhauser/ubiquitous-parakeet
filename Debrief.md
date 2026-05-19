# Debrief: Customer Support Triage Agent

## 1. Project Goal

Build a Python CLI that accepts a free-text customer support ticket, uses Claude to classify it (category, urgency, summary), and routes it to a category-specific handler that produces a mock resolution. The end result demonstrates a two-stage LLM pipeline — a common pattern in production triage and routing systems.

---

## 2. End-to-End Process

1. **Spec before code.** Wrote `SPECS.md` as the single source of truth for architecture, component responsibilities, error handling, and verification cases before touching any implementation files.

2. **Generated project conventions.** Used `/init` to produce `CLAUDE.md` with behavioral guidelines (simplicity first, surgical changes, goal-driven execution), establishing shared norms early.

3. **Test-driven development.** Wrote all tests in `tests/test_agent.py` and `tests/test_cli.py` before writing a single line of implementation — each test was run, watched fail, then made to pass.

4. **Implemented `agent.py`.** Built the triage classifier, the private `_handle()` helper, three handler functions, the `HANDLERS` dispatcher dict, and the `route()` function.

5. **Implemented `triage.py`.** Built the CLI with dependency injection — `main()` accepts `argv`, `stdin`, `isatty`, `env`, and `client_factory` as explicit parameters so it can be fully tested without touching the real OS or the real API.

6. **Verified live.** Ran the six canonical test tickets from `SPECS.md` against the real Anthropic API and confirmed correct category/urgency classification and contextually relevant handler responses.

---

## 3. Key Decisions

### Two-stage LLM pipeline (classify → dispatch → handle)

The triage call and the handler call are deliberately separate API calls with separate system prompts. This keeps each model invocation small and single-purpose: the classifier only classifies; the handler only resolves. Collapsing them into one call would require a more complex prompt and produce less reliable structured output.

### Tool-forced structured output (not "respond in JSON")

The triage call uses `tool_choice={"type": "tool", "name": "submit_triage"}` to force the model to call a specific tool with a validated JSON schema. Free-form "return JSON" prompts can produce markdown fences, prose preambles, or schema drift — all of which require fragile parsing fallbacks. Tool use gives you a guaranteed-valid object at the SDK layer.

### Dispatcher dict, not if/elif

`HANDLERS = {"billing": handle_billing, ...}` is closed over the handler functions. `route()` is a one-liner. Adding a new category is one dict entry and one function — no branching logic to maintain.

### Private `_handle()` helper

All three handlers share identical logic: build a user message, call the API, extract the text block. A single private `_handle(system_prompt, ...)` function DRYs this up without over-abstracting. The public `handle_billing/technical/general` functions remain explicit named symbols for testability and the `HANDLERS` dict.

### Dependency injection in `main()`

`main(argv, stdin, isatty, env, client_factory)` receives all I/O dependencies explicitly. This makes the CLI fully testable without patching `sys` or `os` — tests pass `io.StringIO`, a dict, and a lambda returning a fake client.

### Minimal dependency footprint

`anthropic` only. No `rich`, `colorama`, `pydantic`, or `python-dotenv`. Every dependency that isn't mandatory is a surface for future breakage and an onboarding cost.

---

## 4. Tradeoffs Considered

| Decision | Alternative | Why we didn't |
|---|---|---|
| Two API calls per ticket | Single combined prompt | Less reliable structured output; harder to reason about; defeats the demo's purpose of showing a classify-then-route pipeline |
| Tool-forced structured output | `"Respond only in JSON"` prompt | Parsing free-form JSON is fragile; tool use gives schema validation for free |
| In-file fake client for tests | `unittest.mock` or `vcrpy` | Mocks couple tests to implementation internals; `vcrpy` needs recorded cassettes to stay fresh. Fakes are explicit and fast |
| Dependency injection in `main()` | Patching `sys.argv`, `os.environ` | Patching global state is brittle; injection makes the contract explicit and tests portable |
| No retry logic | Exponential backoff | This is a one-shot demo CLI; the user can re-run. Adding retries adds complexity with no value here |
| `claude-opus-4-7` default | `claude-sonnet-4-6` | Spec called for the most capable model; users who want lower latency/cost can swap the constant in `agent.py` |

---

## 5. What I'd Do Differently (with more time / in production)

**Prompt caching.** The system prompts (`TRIAGE_SYSTEM_PROMPT`, `BILLING_SYSTEM_PROMPT`, etc.) are static strings sent on every call. In production, these should be cached with Anthropic's prompt caching feature to reduce latency and cost — especially on the handler calls which have longer system prompts.

**Streaming on handler responses.** The handler resolution can be several paragraphs. Streaming the response would make the CLI feel significantly more responsive instead of blocking until the full response arrives.

**Retry/backoff.** The current `try/except anthropic.APIError` exits immediately. In production, transient rate limits and network errors should be retried with exponential backoff. The Anthropic SDK provides `max_retries` at client construction; enabling it would be a one-liner change.

**Configurable model selection.** The model is hardcoded as a module-level constant. In a real deployment you'd want this configurable via environment variable or a config file — different teams may want different latency/cost/quality tradeoffs.

**Structured logging.** `print()` to stderr is fine for a CLI demo. In production, structured JSON logs (with ticket ID, category, urgency, and latency per API call) are needed for observability and alerting.

**More urgency granularity in handler prompts.** The handlers currently receive urgency in the user message but don't adjust their tone or escalation path based on it. A `high`-urgency ticket should produce a different response style (faster escalation path, more explicit SLA commitments) than a `low`-urgency ticket.

---

## 6. What Went Well

**Clean separation of concerns.** `triage.py` is purely I/O — it gathers input, formats output, handles errors. `agent.py` is purely logic — it makes API calls and returns data. This boundary made both files easy to read, test, and modify independently.

**Tool-forced structured output was reliable.** In live testing across all six verification cases, the `submit_triage` tool was called correctly on the first attempt every time. No JSON parsing, no fallback logic needed.

**Dependency injection made tests genuinely useful.** The `main()` injection pattern let `test_cli.py` cover the full request-to-output path — including both API calls — with no mocking, no patching, and no network. Tests are fast, deterministic, and read like documentation.

**The spec held up.** `SPECS.md` was written before implementation and ended up matching the shipped code almost exactly. Writing the spec first forced decisions (tool-forced output, dispatcher dict, injection pattern) to be made deliberately rather than discovered during coding.

**Single-file test infrastructure.** The in-file fake client classes (`FakeBlock`, `FakeResponse`, `FakeClient`) are fewer than 30 lines total and cover the full fake surface area. No dependencies, no fixtures shared across files, no magic.
