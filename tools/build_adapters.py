#!/usr/bin/env python3
"""Generate the per-agent instruction files from the single source of truth,
docs/agent-playbook.md.

    python3 tools/build_adapters.py          # rewrite the files
    python3 tools/build_adapters.py --check  # exit 1 if any file is out of date (used by CI)
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NOTE = ("<!-- GENERATED from docs/agent-playbook.md by tools/build_adapters.py. "
        "Edit the playbook, then re-run the script. -->\n")

SKILL_FRONT = """---
name: time-assistant
description: Export an approved week of time and expenses from the source time system (reference setup Kleer) into a week file that the local time-assistant script replicates into TimeKeeper. Use when the user asks to sync, replicate or copy their week to TimeKeeper.
---
"""

AGENTS_HEAD = """# AGENTS.md

Instructions for AI coding/automation agents that read `AGENTS.md` (OpenAI Codex, many
other agents and IDEs). If you were asked to "sync the week", follow the playbook below.
If you were asked to work on this repository, run the tests with
`python3 -m unittest discover -s tests -p "test_*.py"`, regenerate the instruction files
with `python3 tools/build_adapters.py` after editing `docs/agent-playbook.md`, and never
commit `config.json`, `.tk_user` or `week-*.json` files (they are git-ignored on purpose).

"""


def playbook() -> str:
    with open(os.path.join(ROOT, "docs", "agent-playbook.md"), encoding="utf-8") as f:
        return f.read().rstrip() + "\n"


def render() -> dict:
    p = playbook()
    return {
        "AGENTS.md": NOTE + AGENTS_HEAD + p,
        ".github/copilot-instructions.md": NOTE + p,
        "integrations/claude/time-assistant/SKILL.md": SKILL_FRONT + NOTE + "\n" + p,
        "integrations/generic/instructions.md": NOTE + p,
    }


def main(argv) -> int:
    stale = []
    for rel, text in render().items():
        path = os.path.join(ROOT, rel)
        old = open(path, encoding="utf-8").read() if os.path.exists(path) else None
        if old == text:
            continue
        stale.append(rel)
        if "--check" not in argv:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
    if "--check" in argv:
        for rel in stale:
            print(f"out of date: {rel}")
        return 1 if stale else 0
    print("updated:", ", ".join(stale) if stale else "nothing, all files already current")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
