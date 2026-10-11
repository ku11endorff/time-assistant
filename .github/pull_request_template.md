## What and why

<!-- One topic per pull request. -->

## Tested

- [ ] `python3 -m unittest discover -s tests -p "test_*.py"`
- [ ] `python3 tools/build_adapters.py --check`
- [ ] Against a real account (say which system and what you ran), or only against fakes:
- [ ] Changed or new data? The semantic table in `docs/data-convention.md` is updated

## New target? (see docs/adding-a-target.md)

- [ ] `time_assistant/targets/<type>.py`, added to `BUILTIN`
- [ ] `tests/test_target_<type>.py` with a `TargetContract` subclass and a fake API
- [ ] `docs/targets/<type>.md` and a row in the README's *Supported targets* table
- [ ] A column for the target in the semantic table at the end of `docs/data-convention.md`, every row filled
- [ ] Standard library only; no real ids, names or credentials anywhere
