# CLAUDE.md

Behavioral guidelines to reduce common LLM coding mistakes. Merge with project-specific instructions as needed.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Customer support triage agent: a Python CLI that takes a free-text support ticket, uses Claude to classify it (category + urgency + summary), and routes it to a category-specific handler that produces a mock resolution.

The full design — architecture, file layout, component responsibilities, error handling, and verification cases — is in `SPECS.md`. Read it before making non-trivial changes; it is the source of truth for *why* the code is shaped the way it is.

## Setup

```
pip install -r requirements.txt
cp .env.example .env   # then edit .env to set ANTHROPIC_API_KEY
```

The script reads `ANTHROPIC_API_KEY` from the environment. On Windows PowerShell you can also set it inline: `$env:ANTHROPIC_API_KEY = "sk-ant-..."`.

## Running

```
python triage.py "ticket text here"          # argument
echo "ticket text" | python triage.py        # stdin
python triage.py                             # interactive (Ctrl-Z then Enter on Windows to submit)
```

See `SPECS.md` → **Verification** for the canonical test tickets covering each category and urgency level.

## Architecture (key decisions)

- **Two-stage LLM pipeline.** `triage()` classifies, then a dispatcher dict routes to one of three handler functions (`handle_billing`, `handle_technical`, `handle_general`). Each handler makes its own Claude call with a category-specific system prompt. Don't collapse this into a single call — the separation is the point of the demo.
- **Structured output via tool use, not "respond in JSON".** The triage call forces a `submit_triage` tool via `tool_choice={"type": "tool", "name": "submit_triage"}`. This guarantees a valid schema-conforming object; do not switch to free-form JSON parsing.
- **Default model:** `claude-sonnet-4-6` for both calls.
- **Single dependency:** `anthropic` only. No `rich`, `colorama`, `pydantic`, or `python-dotenv` — keep it minimal.
- **No tests, no retries, no logging framework.** This is a demo CLI; see `SPECS.md` → **What's Out of Scope** before adding any of these.

## File map

- `triage.py` — CLI entry point. Input gathering (arg / stdin / interactive) and output formatting only.
- `agent.py` — Core logic: triage classifier, handler functions, dispatcher dict, system prompts, tool schema.
