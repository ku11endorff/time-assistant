# Adding a target

A target is one system that receives copies of the approved week. Adding one touches
three places and nothing else:

| File | What |
|---|---|
| `time_assistant/targets/<type>.py` | The target: a `Target` subclass that talks to the system's API |
| `tests/test_target_<type>.py` | A fake of the API, the shared contract suite, and your own specific tests |
| `docs/targets/<type>.md` | The setup page: ids, field mapping, behaviour, troubleshooting |

Plus one line in `time_assistant/targets/__init__.py` (`BUILTIN`) and one row in the
README's *Supported targets* table. `tests/test_registry.py` fails until the docs page
and the contract tests exist, so CI tells you when the target is complete.

Rules that hold for every target:

- **Standard library only.** No `pip install`; use `urllib`, `json`, `base64`, ...
- **No real data in the repository.** Every id, name and comment in tests and docs is made up.
- **Secrets only through `secrets`.** Declare `secrets = ("password",)` or `("token",)`;
  the engine looks them up per target. Never read them from config.json or print them.
- **Read your own scope only.** `existing()` returns only rows of this target's account
  *and* project, so two targets sharing an account never touch each other's rows.

## 1. Before you start

Find out from the system's API documentation:

- How to authenticate (Basic Auth, API token, OAuth client credentials, ...).
- How to list a user's time rows (and expense rows) for a date range.
- How to create, update and delete a row, and which fields are required.
- Where the row can carry the tag. A free-text comment is the usual place; a dedicated
  "external reference" field is even better.
- Whether the system locks or reports per month (then `split_by_month = True`).

## 2. The module

`time_assistant/targets/example.py`, a skeleton for a token-based JSON API:

```python
"""ExampleTime (api.example.invalid) as a target. Setup: docs/targets/example.md."""
from __future__ import annotations

import json
import urllib.error
import urllib.request

from .. import markers
from .base import Existing, Target, Wanted


class ExampleAPI:
    def __init__(self, token, base="https://api.example.invalid"):
        self.base, self.headers = base, {"Authorization": f"Bearer {token}",
                                         "Content-Type": "application/json"}

    def call(self, method, path, body=None):
        req = urllib.request.Request(self.base + path, method=method, headers=self.headers,
                                     data=json.dumps(body).encode() if body is not None else None)
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode() or "null")
        except urllib.error.HTTPError as e:
            raise SystemExit(f"ExampleTime {method} {path} -> HTTP {e.code}")


class ExampleTarget(Target):
    type = "example"
    display_name = "ExampleTime"
    supports_expenses = False
    split_by_month = False
    secrets = ("token",)
    required_settings = ("project",)
    time_map_fields = ("task",)
    write_pause = 0.1

    def __init__(self, config, secrets=None, api=None):
        super().__init__(config, secrets)
        self.project = self.settings.get("project")
        self.api = api or ExampleAPI((secrets or {}).get("token", ""))

    @classmethod
    def identity(cls, config):
        return (config.get("settings") or {}).get("project")

    def existing(self, kind, d_from, d_to):
        rows = self.api.call("GET", f"/entries?project={self.project}&from={d_from}&to={d_to}")
        return [Existing(id=r["id"], key=markers.find(r.get("note"), kind), date=r["day"],
                         project=r["project"], raw=r) for r in rows or []]

    def build(self, kind, item, mapping):
        return Wanted(project=self.project, payload={
            "project": self.project, "day": item["date"], "task": mapping["task"],
            "minutes": round(item["hours"] * 60), "note": self.comment(kind, item, mapping)})

    def same(self, kind, existing, wanted):
        have, want = existing.raw, wanted.payload
        return (all(have.get(k) == want[k] for k in ("day", "task", "minutes"))
                and markers.normalise(have.get("note")) == markers.normalise(want["note"]))

    def create(self, kind, wanted):
        self.api.call("POST", "/entries", wanted.payload)

    def update(self, kind, existing, wanted):
        self.api.call("PUT", f"/entries/{existing.id}", wanted.payload)

    def delete(self, kind, existing):
        self.api.call("DELETE", f"/entries/{existing.id}")

    def discover(self):
        for p in self.api.call("GET", "/projects") or []:
            print(f"  {p['id']}\t{p['name']}")
```

Then add it to `BUILTIN` in `time_assistant/targets/__init__.py`:

```python
from .example import ExampleTarget
BUILTIN = (TimeKeeperTarget, ExampleTarget)
```

Notes:

- `self.comment(kind, item, mapping)` gives the usual comment with the tag appended. If
  the system has a separate reference field, put `markers.tag(kind, item["id"])` there
  instead and read it back with `markers.find`.
- `same()` must compare everything `build()` sets, and compare comments with
  `markers.normalise()`.
- Daily allowances arrive in `build("expense", item, mapping)` with `item["kind"] ==
  "allowance"` and their `allowance_map` entry as `mapping`. Set
  `supports_allowances = True` only if the system can store them; the contract suite then
  tests them too.
- Raise `SystemExit("...")` with a readable message for API errors; the engine reports it
  per target and month and keeps going with the rest.
- `check_settings()` can add offline checks (types, URL format) beyond the declared fields.
- `identity()` returns where the rows live (account + project). `check-config` refuses
  two targets with the same identity.

## 3. The tests

`tests/test_target_example.py`: a fake API with the same methods as the real client,
the shared contract, and tests for anything specific to the system:

```python
import unittest

import _paths  # noqa: F401
from target_contract import TargetContract
from time_assistant.targets.example import ExampleTarget


class FakeExampleAPI:
    def __init__(self):
        self.rows, self.next_id = [], 1

    def call(self, method, path, body=None):
        ...   # keep rows in self.rows; honour project, from and to on GET


class ExampleContract(TargetContract, unittest.TestCase):
    target_type = "example"

    def new_backend(self):
        return FakeExampleAPI()

    def make_target(self, config, backend):
        t = ExampleTarget(config, {"token": "x"}, api=backend)
        t.write_pause = 0
        return t

    def target_config(self):
        return {"name": "client", "type": "example", "source_project_ids": [1000001],
                "settings": {"project": "P1"}, "time_map": [{"source_activity_id": 1001, "task": "T1"}]}

    def add_manual_row(self, backend, config, kind, date):
        backend.rows.append({"id": 999, "project": "P1", "day": date, "task": "T1",
                             "minutes": 60, "note": "typed by hand"})

    def other_scope_config(self):
        return dict(self.target_config(), name="other", settings={"project": "P2"})
```

The contract checks creating, safe re-runs, updates, removed entries, rows typed by
hand, date ranges, expenses, receipts and allowances (skipped if not supported), and that
two targets in one account stay apart. Add your own tests for payload shape, unit conversions, error
handling and pagination. Run everything:

```bash
python3 -m unittest discover -s tests -p "test_*.py"
```

## 4. The docs page

`docs/targets/example.md`, following [timekeeper.md](targets/timekeeper.md): what is
supported, setup steps and where each id comes from, a config snippet, the field
mapping, behaviour worth knowing, troubleshooting. Then add the row to the README's
*Supported targets* table.

## 5. Try it for real

With your own account, after the tests pass:

```bash
python3 sync.py discover --target <name>
python3 sync.py check-config
python3 sync.py plan --week week-YYYY-Www.json --target <name>
```

Write to a test project first if the system has one. Say in the pull request what you
tested against a real account and what only against the fake.
