# Changelog

What changed in each version of time-assistant, and what to do when you update to it.
How to update: [docs/updating.md](docs/updating.md). Find your version with
`python3 sync.py version`.

Each version has an **Upgrading** list. Read it for every version between yours and the
new one. The agent playbook version is listed too: when it changes, refresh your agent's
instructions.

## [0.4.1] - 2026-10-11

Agent playbook: 4

### Changed
- Every pull request now says whether it is a major, minor or patch change and bumps the
  version to match; CI checks it, and merging publishes the GitHub release automatically
  ([CONTRIBUTING.md](CONTRIBUTING.md#versioning)).

### Upgrading
- Nothing to do.

## [0.4.0] - 2026-10-11

Agent playbook: 4

### Added
- `python3 sync.py version` shows the version, the agent playbook it expects and the git
  state of your checkout.
- Week files carry `playbook_version`. `validate`, `plan` and `apply` warn when a week was
  exported with older (or newer) agent instructions than this version expects, so a stale
  skill or pasted instruction no longer goes unnoticed.
- `check-config` adds a `NOTE` for optional features a target supports but your config
  does not use yet, e.g. daily allowances.
- This changelog, [docs/updating.md](docs/updating.md), and GitHub releases built from
  version tags.
- A semantic data table at the end of [docs/data-convention.md](docs/data-convention.md):
  every piece of data in the week file, Kleer and each target, one column per target.

### Changed
- The Claude Code skill is now linked into `~/.claude/skills/` instead of copied, so
  `git pull` updates it ([docs/agents.md](docs/agents.md)).

### Upgrading
- Refresh your agent's instructions (playbook 3 → 4): the agent now writes
  `playbook_version` into the week file. Until you do, every run shows a `WARN` about it.
- Claude Code: replace your copied skill with the link from docs/agents.md, once.
- Run `python3 sync.py check-config` and read the `NOTE` lines.

## [0.3.0] - 2026-10-11

Agent playbook: 3

### Added
- Daily allowances (traktamente), domestic and foreign. In the week file they are expenses
  with `"kind": "allowance"` and `"allowance_type"`; each target opts in with an
  `allowance_map`. TimeKeeper writes them as *Övrigt* rows with the inrikes / utrikes
  traktamente wage code.
- TimeKeeper `discover` lists wage codes.

### Fixed
- A target without an `expense_map` no longer fails the dry run on every expense; its
  expenses are listed as not replicated.

### Upgrading
- Refresh your agent's instructions (playbook 2 → 3) so it exports allowances.
- To replicate allowances to a target, add an `allowance_map` to it
  ([docs/configuration.md](docs/configuration.md#allowance_map)). Without one, nothing
  changes: allowances are listed, not written.

## [0.2.0] - 2026-10-11

Agent playbook: 2

### Changed (breaking)
- Several targets instead of one TimeKeeper project. `config.json` has a new format
  (`version: 2`, a `targets` list). Old files are refused with a pointer to
  `migrate-config`.
- Each target's password is stored under its own keychain name,
  `time-assistant:<target name>`, and `sync.py` reads it itself. `tk.sh` is deprecated.
- New rows are tagged `[ta:t:<id>]` / `[ta:e:<id>]`; rows with the old `[kleer:…]` tags
  still match.
- License changed from MIT to Apache License 2.0.

### Added
- `check-config`, `targets`, `--target NAME`, `"enabled": false`, per-target
  `accepted_statuses`.
- `source.rerun_hint` (it was `approval.rerun_hint` in the old format) sets the last
  sentence of the "week not approved" error.

### Upgrading
- `python3 sync.py migrate-config` once; it keeps `config.json.bak-v1`.
- Store the password again under the name it prints, e.g.
  `security add-generic-password -s time-assistant:timekeeper -a password -U -w`.
- Refresh your agent's instructions (playbook 1 → 2) and run `python3 sync.py` instead of
  `./tk.sh`.

## [0.1.0] - 2026-10-11

Agent playbook: 1

First release: replicate an approved Kleer week into one TimeKeeper project.
