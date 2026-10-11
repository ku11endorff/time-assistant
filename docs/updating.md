# Updating time-assistant

Your own setup lives in files git never touches (`config.json`, `.tk_user`, `week-*.json`)
and in your OS keychain, so updating is: get the new code, read what changed, adjust your
config if you want the new features, refresh your agent's instructions, dry run.

## 1. See where you are

```bash
python3 sync.py version
```

```
time-assistant 0.4.0
agent playbook 4  (week files should carry "playbook_version": 4)
git checkout   v0.4.0
```

The newest version is on the repository's **Releases** page;
[CHANGELOG.md](../CHANGELOG.md) lists every version.

## 2. Get the new code

| You have | Do |
|---|---|
| A clone of the main repository | `git pull` |
| A fork on GitHub | On your fork's page: **Sync fork → Update branch**. Then `git pull` in your copy |
| A fork with your own changes (e.g. your own target) | Once: `git remote add upstream https://github.com/ku11endorff/time-assistant.git`. Then `git fetch upstream` and `git merge upstream/main` (or a release tag such as `v0.4.0`). Keeping your changes in their own files, such as `time_assistant/targets/<yours>.py`, keeps merges clean |
| A specific release | `git fetch --tags` and `git checkout v0.4.0` |
| A downloaded zip | Download the new release and copy your `config.json` (and `.tk_user`, if you have one) into it |

## 3. Read what changed

Open [CHANGELOG.md](../CHANGELOG.md) and read the **Upgrading** list of every version
newer than the one `version` showed before you updated. It says when you need to run a
command (for example `migrate-config`), change your config, or refresh your agent.

## 4. Check your config

```bash
python3 sync.py check-config
```

- `ERROR` lines must be fixed; nothing runs until they are. An old config format says to
  run `python3 sync.py migrate-config`.
- `NOTE` lines are optional features your targets support that your config does not use
  yet, for example daily allowances. Each note links to the field to add. Ignore them if
  you do not want the feature.

## 5. Refresh your agent's instructions

The agent follows its own copy of [agent-playbook.md](agent-playbook.md). When a release
changes the playbook (the changelog says *Agent playbook: N*), that copy must be updated
too, or the agent keeps exporting the old way.

| Agent | Updated by `git pull`? | Otherwise |
|---|---|---|
| Claude Code with the skill **linked** ([agents.md](agents.md)) | yes | — |
| Claude Code with the skill **copied** | no | Replace the copy with the link from [agents.md](agents.md), once |
| Claude desktop / web app (skill uploaded in settings) | no | Upload `integrations/claude/time-assistant/` again |
| Agents that read `AGENTS.md`, GitHub Copilot (`.github/copilot-instructions.md`) | yes | — |
| Custom GPT, ChatGPT Project, Copilot Studio, anything you pasted instructions into | no | Paste `integrations/generic/instructions.md` again |

You do not have to remember this: every week file carries the `playbook_version` it was
made with, and `validate`, `plan` and `apply` show a `WARN` when it does not match what
this version of time-assistant expects.

## 6. Dry run

Export a week with your agent and run

```bash
python3 sync.py plan --week week-YYYY-Www.json
```

before the first `apply` on the new version. No `WARN` about the playbook version and a
plan that looks like last week's means you are done.
