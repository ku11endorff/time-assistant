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
| `config.json` fields | `time_assistant/config.py`, `config.example.json`, `docs/configuration.md`. A new *optional* field also gets a `NOTE` in `config.feature_notes()`, so people who update learn it exists |
| Week file | `time_assistant/week.py`, `schema/week.schema.json`, `docs/data-convention.md` (a new field also gets a row in the semantic table, filled for every system) |
| Agent instructions | `docs/agent-playbook.md` only, then `python3 tools/build_adapters.py` to regenerate `AGENTS.md`, `.github/copilot-instructions.md` and `integrations/`. If the change affects what the agent writes, bump `PLAYBOOK_VERSION` in `time_assistant/week.py` and the two numbers in the playbook (tests check they match), and say so in the changelog |

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
- Every pull request is a release: tick Major, Minor or Patch in its description and bump
  the version to match (see [Versioning](#versioning)).
- `python3 -m unittest discover -s tests -p "test_*.py"` and
  `python3 tools/build_adapters.py --check` pass (CI runs both on Python 3.9 and 3.12).
- Update the docs that describe what you changed.

## Versioning

Versions are `MAJOR.MINOR.PATCH`, and **every pull request bumps one of them**. The pull
request template asks which; pick by what happens to someone who updates:

| Bump | When | Examples |
|---|---|---|
| **Major** (x.0.0) | Existing setups must change something, or something stops working | A config format that needs `migrate-config`; a week-file change that makes older agent output fail `validate`; a removed command or option; row tags that no longer match rows already written; dropping a target |
| **Minor** (0.x.0) | A new capability; existing setups keep working unchanged | A new target; a new optional config field; a new command; daily allowances; a new playbook version whose old week files still validate (with a `WARN`) |
| **Patch** (0.0.x) | No new capability | A bug fix; docs; tests; CI or contributor process |

When in doubt between two, take the bigger one. In the pull request:

1. Tick exactly one of Major / Minor / Patch under **Version** in the description.
2. Set `__version__` in `time_assistant/__init__.py` to the next version after `main`'s:
   from 0.4.1, major → 1.0.0, minor → 0.5.0, patch → 0.4.2.
3. Add a `## [X.Y.Z] - YYYY-MM-DD` section at the top of [CHANGELOG.md](CHANGELOG.md) with
   an `Agent playbook: N` line, what changed, and an `### Upgrading` list ("Nothing to do."
   if nothing).

The `version` workflow (`tools/check_version.py`) fails the pull request if no box or more
than one is ticked, if the version is not the next one for that bump, or if the changelog
section is missing. If another pull request is merged first, update your branch from
`main` and bump again from the new version.

## Releasing

Nothing to do by hand. When a pull request is merged, the `release` workflow sees a new
version on `main`, runs the tests, checks that version and changelog agree
(`tools/release_notes.py`), and publishes a GitHub release with tag `vX.Y.Z` and that
version's changelog section as its notes. It can also be started by hand from the
repository's *Actions* tab.

## License

By contributing you agree that your contribution is licensed under the Apache License 2.0
([LICENSE](LICENSE)).
