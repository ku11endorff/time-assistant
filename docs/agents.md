# Using time-assistant with your AI agent

The agent only does the **export**: read the week from your time system, check approval,
write `week-YYYY-Www.json`. Writing to your targets (TimeKeeper and any others) is always
done by `sync.py` on your own machine, after a dry run you confirm. So any agent works that can

1. read your source data (an MCP server or API connector, or data you paste or upload), and
2. follow written instructions and hand you a JSON file (saved by the agent, or copied by you).

The instructions are identical for every agent: [`docs/agent-playbook.md`](agent-playbook.md).
`python3 tools/build_adapters.py` copies it into the format each tool picks up, so you
never edit more than one file.

| Agent | What to use | How it gets your data |
|---|---|---|
| **Claude** (desktop / web apps, Claude Code) | `integrations/claude/time-assistant/SKILL.md` as a skill. In Claude Code **link** the folder (below), so `git pull` keeps it current. In the Claude apps upload the folder through the skills settings, and upload it again after updates that change the playbook | Kleer MCP connector; connect your project folder so the agent can write the week file there |
| **ChatGPT / OpenAI Codex** and other agents that read `AGENTS.md` | `AGENTS.md` at the repo root is picked up automatically by agents that support it. For a Custom GPT or Project, paste `integrations/generic/instructions.md` into its instructions | A connector/MCP for your time system if your plan offers one; otherwise export the week from the time system and upload or paste it, and save the JSON the agent returns |
| **GitHub Copilot** (agent mode in your editor) | `.github/copilot-instructions.md` is read automatically from the repo | Needs a tool that can read your time system; otherwise paste an export |
| **Microsoft Copilot** (Copilot Studio agents and similar) | Paste `integrations/generic/instructions.md` into the agent's instructions | Via a connector or action you configure for your time system, or pasted data |
| **Any other agent** | Paste `integrations/generic/instructions.md` as system prompt or instructions | Whatever it can reach |
| **No agent** | Write the week file by hand from `examples/week.example.json` | `python3 sync.py validate --week FILE` tells you what is wrong |

Check each agent's own documentation for where instructions, skills or connectors are
configured; menus change often.

### Claude Code: link the skills, don't copy them

There are two: `time-assistant` (the weekly export) and `time-assistant-setup` (the
interactive setup guide, hand-written). Run this once from the time-assistant folder:

```bash
mkdir -p ~/.claude/skills
ln -sfn "$PWD/integrations/claude/time-assistant"       ~/.claude/skills/time-assistant
ln -sfn "$PWD/integrations/claude/time-assistant-setup" ~/.claude/skills/time-assistant-setup
```

The whole routine in Claude, with a project that holds your instructions and the Kleer
connector: [claude-project-setup.md](claude-project-setup.md). From your phone:
[cloud-sessions.md](cloud-sessions.md).

A link always points at the files in your checkout, so every `git pull` updates the skill
as well. If you copied the folder before, remove the copy first
(`rm -r ~/.claude/skills/time-assistant`), then run the two lines above. For one project
only, link into `.claude/skills/` inside that project instead.

### Keeping instructions current

Instructions that are copied or pasted into an agent do not change when you update
time-assistant. Every week file says which playbook version made it, and `sync.py` warns
when that differs from what it expects; [updating.md](updating.md) lists what to refresh
for each agent.

## First test with a new agent

1. Give it the instructions and access to your source data.
2. Ask: *"Export last week for time-assistant."*
3. It must (a) name the exact dates, (b) stop with a clear message if any entry is not
   approved, (c) ask about receipts if an expense on your project has one, (d) produce a
   file that passes `python3 sync.py validate --week week-….json`.
4. Run `python3 sync.py plan --week week-….json` and read it before any `apply`.

If an agent cannot do (b), do not use it for this: the approval check in `sync.py` is
the second line of defence, but the first should not be missing.

## Credentials

Never paste a target's password or token into an AI chat. The instructions tell agents
to refuse it, and `sync.py` reads it from your keychain on your own machine
([configuration.md](configuration.md#secrets)).
