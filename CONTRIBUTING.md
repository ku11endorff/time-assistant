# Contributing

Thanks for helping. time-assistant is meant to grow one target system at a time, by the
people who need each one. Fixes, docs and new source-system notes are just as welcome.

## Ground rules

- **Standard library only**, Python 3.9+. No dependencies, so anyone can run it after a
  `git clone`.
- **No real data.** Ids, names, comments, receipts and accounts in code, tests, docs and
  issues are made up. Never commit `config.json`, `.tk_user` or `week-*.json` (they are
  git-ignored). Redact dry-run output before pasting it into an issue.
- **No secrets anywhere** except the OS keychain or environment variables at run time.
- **Safety first.** Changes must keep the guarantees in
  [docs/architecture.md](docs/architecture.md#guarantees-and-where-they-live): approval gate,
  dry run, tags, hand-typed rows untouched, no deletes unless asked.

## Setup

```bash
git clone https://github.com/<you>/time-assistant.git
cd time-assistant
python3 -m unittest discover -s tests -p "test_*.py"
```

The tests are offline and need no accounts: targets are tested against fakes of their APIs.

## What goes where

| Change | Files |
|---|---|
| A new target | [docs/adding-a-target.md](docs/adding-a-target.md); this includes a new column in the [semantic table](docs/data-convention.md#semantic-data-convention-across-systems) of `docs/data-convention.md` |
| Behaviour shared by all targets | `time_assistant/engine.py`, tested in `tests/test_engine.py` (and `tests/target_contract.py` if it is something every target must do) |
| `config.json` fields | `time_assistant/config.py`, `config.example.json`, `docs/configuration.md` |
| Week file | `time_assistant/week.py`, `schema/week.schema.json`, `docs/data-convention.md` (a new field also gets a row in the semantic table, filled for every system) |
| Agent instructions | `docs/agent-playbook.md` only, then `python3 tools/build_adapters.py` to regenerate `AGENTS.md`, `.github/copilot-instructions.md` and `integrations/` |

## The semantic data table

The table at the end of [docs/data-convention.md](docs/data-convention.md#semantic-data-convention-across-systems)
is the one place that shows how each piece of data is named and converted in every
system: one row per meaning, one column per system (week file, Kleer, then each target).
Keep it complete:

- **New target:** add its column on the right and fill every row.
- **New data** (a week-file field, a new kind of entry): add a row and fill it for every
  column.
- **Changed mapping** in a target: update its cells.

`—` means the system has no such field, *not sent* that time-assistant leaves an existing
field alone, *not replicated* that the target does not take that data at all. CI
(`tests/test_registry.py`) fails if a built-in target has no column or a row is missing
a cell.

## Pull requests

- One topic per pull request; describe what you tested against a real account and what
  only against fakes.
- `python3 -m unittest discover -s tests -p "test_*.py"` and
  `python3 tools/build_adapters.py --check` pass (CI runs both on Python 3.9 and 3.12).
- Update the docs that describe what you changed.

## License

By contributing you agree that your contribution is licensed under the Apache License 2.0
([LICENSE](LICENSE)).
