# Changelog

What changed in each version of time-assistant, and what to do when you update to it.
How to update: [docs/updating.md](docs/updating.md). Find your version with
`python3 sync.py version`.

Each version has an **Upgrading** list. Read it for every version between yours and the
new one. The agent playbook version is listed too: when it changes, refresh your agent's
instructions.

## [0.5.0] - 2026-10-26

Agent playbook: 5

### Added
- **Run from your phone.** A Claude Code cloud session can run the whole routine. With
  `TIME_ASSISTANT_AUTH=proxy` the TimeKeeper login is added by the cloud environment's
  network secret and `sync.py` looks up no password; with the file `config.json` missing,
  the configuration is read from `TIME_ASSISTANT_CONFIG_JSON`. `tools/make_cloud_env.py`
  builds both lines. [docs/cloud-sessions.md](docs/cloud-sessions.md)
- **TimeKeeper receipt category and "paid by".** Optional `expense_map` keys
  `receipt_category_id` and `paid_by` (`self` / `company`). Some accounts refuse the receipt
  wage code without a category (`HTTP 400 ... Lönekoden Kvitto är inte längre tillgänglig`).
  `discover` lists the receipt categories; `check-config` shows a `NOTE` until they are set.
- **VAT.** Optional `vat_ore` on expenses, sent as the VAT amount.
- **Half-day allowances.** Optional `quantity` (`1` or `0.5`) on allowances; one allowance
  per calendar day, the price is the day's amount divided by the quantity.
- `tools/save_receipt.py`: decode a receipt fetched from Kleer (`getExpenseFileImage`),
  writing the file only if it is a real JPEG, PNG or PDF.
- Documentation: [how it works](docs/how-it-works.md), a full
  [getting started](docs/getting-started.md) guide, a
  [Claude project setup](docs/claude-project-setup.md), and an interactive setup skill,
  `integrations/claude/time-assistant-setup`.
- `examples/week.example-expenses.json`: a week with a receipt, a foreign-currency expense
  and per-day allowances.

### Changed
- Agent playbook 5: the agent exports `vat_ore`, one allowance object per day, the expense
  project id Kleer gives (which differs from the time entries' client-project id; list every
  id in `source_project_ids`), converted amounts for foreign currency, and, in cloud
  sessions, fetches receipts from Kleer by their file id.
- CI: the test job is pinned to `ubuntu-24.04`; `ubuntu-latest` moved to 26.04, which has no
  Python 3.9 build for `setup-python`, so the 3.9 job (and with it the whole matrix) failed.

### Fixed
- A receipt that was already attached to an expense in TimeKeeper was not recognised
  (TimeKeeper names the field `originalFileName`), so a re-run could attach it again.

### Upgrading
- Refresh your agent's instructions (playbook 4 → 5); until you do, every run shows a `WARN`.
  Claude Code: nothing if you linked the skill. Claude apps: upload the skill again.
- Run `python3 sync.py check-config` and read the `NOTE` lines. If your TimeKeeper rejects
  expense rows, set `receipt_category_id` and `paid_by` in `expense_map`
  ([docs/targets/timekeeper.md](docs/targets/timekeeper.md#receipt-category-and-paid-by)).
- If expenses show up as "not replicated", add the expense project id to
  `source_project_ids`.

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
