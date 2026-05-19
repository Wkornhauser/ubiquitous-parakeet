"""Customer support triage CLI.

Usage:
    python triage.py "ticket text"
    echo "ticket text" | python triage.py
    python triage.py  # interactive — paste ticket, then Ctrl-Z (Windows) / Ctrl-D (Unix)
"""
import os
import sys

import anthropic

import agent


def get_ticket(argv, stdin, isatty):
    """Read ticket text from argv, stdin (piped), or interactive prompt."""
    if len(argv) > 1 and argv[1].strip():
        return argv[1].strip()
    if isatty:
        print(
            "Paste ticket text, then press Ctrl-Z (Windows) or Ctrl-D (Unix) "
            "followed by Enter:",
            file=sys.stderr,
        )
    return stdin.read().strip()


def main(argv, stdin, isatty, env, client_factory):
    if not env.get("ANTHROPIC_API_KEY"):
        print(
            "Error: ANTHROPIC_API_KEY is not set. Copy .env.example to .env "
            "and add your key, or export ANTHROPIC_API_KEY in your shell.",
            file=sys.stderr,
        )
        return 1

    ticket = get_ticket(argv, stdin, isatty)
    if not ticket:
        print(
            "Error: ticket is empty. Provide ticket text as an argument or "
            "via stdin.",
            file=sys.stderr,
        )
        return 1

    client = client_factory()
    try:
        triage_result = agent.triage(ticket, client)
        resolution = agent.route(ticket, triage_result, client)
    except anthropic.APIError as exc:
        print(f"Error calling Anthropic API: {exc}", file=sys.stderr)
        return 1
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print("=== Triage ===")
    print(f"Category: {triage_result['category']}")
    print(f"Urgency:  {triage_result['urgency']}")
    print(f"Summary:  {triage_result['summary']}")
    print()
    print(f"=== Resolution ({triage_result['category']} handler) ===")
    print(resolution)
    return 0


if __name__ == "__main__":
    sys.exit(main(
        argv=sys.argv,
        stdin=sys.stdin,
        isatty=sys.stdin.isatty(),
        env=os.environ,
        client_factory=anthropic.Anthropic,
    ))
