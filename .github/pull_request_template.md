## What and why

<!-- One topic per pull request. -->

## Version

<!-- Tick exactly one, then set __version__ in time_assistant/__init__.py to the next
     version and add its CHANGELOG.md section. CI checks both. Merging publishes the
     release. Which one: CONTRIBUTING.md#versioning -->

- [ ] Major (x.0.0): existing setups must change something, or something stops working
- [ ] Minor (0.x.0): new capability; existing setups keep working unchanged
- [ ] Patch (0.0.x): bug fix, docs, tests or process; no new capability

## Tested

- [ ] `python3 -m unittest discover -s tests -p "test_*.py"`
- [ ] `python3 tools/build_adapters.py --check`
- [ ] Against a real account (say which system and what you ran), or only against fakes:
- [ ] Changed or new data? The semantic table in `docs/data-convention.md` is updated
- [ ] `__version__` bumped and a `CHANGELOG.md` section for it (with an Upgrading step if users must act)
- [ ] Playbook changed what the agent writes? `PLAYBOOK_VERSION` bumped

## New target? (see docs/adding-a-target.md)

- [ ] `time_assistant/targets/<type>.py`, added to `BUILTIN`
- [ ] `tests/test_target_<type>.py` with a `TargetContract` subclass and a fake API
- [ ] `docs/targets/<type>.md` and a row in the README's *Supported targets* table
- [ ] A column for the target in the semantic table at the end of `docs/data-convention.md`, every row filled
- [ ] Standard library only; no real ids, names or credentials anywhere
