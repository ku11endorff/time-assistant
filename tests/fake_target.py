"""An in-memory target for testing the engine without any real system.

It is registered under the types "memory" (time, expenses, receipts) and "memory-basic"
(time only), so test configs can use them like real targets.
"""
import copy
import json
import os

import _paths  # noqa: F401  (puts the repo root on sys.path)
from time_assistant import markers
from time_assistant import targets as registry
from time_assistant.targets import Existing, Target, Wanted

with open(_paths.EXAMPLE_WEEK, encoding="utf-8") as _f:
    WEEK = json.load(_f)


class MemoryBackend:
    """Rows of one account: {"id", "date", "project", "code", "value", "comment"}."""
    def __init__(self):
        self.rows = {"time": [], "expense": []}
        self.files = {}           # row id -> [file names]
        self.next_id = 100
        self.fail = None          # optional callable(kind, payload) -> True to refuse a create


@registry.register
class MemoryTarget(Target):
    type = "memory"
    display_name = "Memory"
    supports_expenses = True
    supports_receipts = True
    split_by_month = True
    required_settings = ("project",)
    time_map_fields = ("code",)
    expense_map_fields = ("code",)

    def __init__(self, config, secrets=None, backend=None):
        super().__init__(config, secrets)
        self.db = backend or MemoryBackend()
        self.project = self.settings.get("project")

    @classmethod
    def identity(cls, config):
        s = config.get("settings") or {}
        return (s.get("account", "default"), s.get("project"))

    def existing(self, kind, d_from, d_to):
        return [Existing(id=r["id"], key=markers.find(r["comment"], kind), date=r["date"],
                         project=r["project"], raw=r)
                for r in self.db.rows[kind]
                if r["project"] == self.project and d_from <= r["date"] <= d_to]

    def build(self, kind, item, mapping):
        value = item["hours"] if kind == "time" else item["amount_ore"]
        return Wanted(payload={"date": item["date"], "project": self.project, "code": mapping["code"],
                               "value": value, "comment": self.comment(kind, item, mapping)},
                      project=self.project)

    def same(self, kind, existing, wanted):
        have = {k: v for k, v in existing.raw.items() if k != "id"}
        want = dict(wanted.payload)
        return (markers.normalise(have.pop("comment")) == markers.normalise(want.pop("comment"))
                and have == want)

    def create(self, kind, wanted):
        if self.db.fail and self.db.fail(kind, wanted.payload):
            raise SystemExit("HTTP 403: period closed")
        self.db.next_id += 1
        self.db.rows[kind].append(dict(wanted.payload, id=self.db.next_id))

    def update(self, kind, existing, wanted):
        rows = self.db.rows[kind]
        rows[:] = [dict(wanted.payload, id=r["id"]) if r["id"] == existing.id else r for r in rows]

    def delete(self, kind, existing):
        self.db.rows[kind][:] = [r for r in self.db.rows[kind] if r["id"] != existing.id]

    def attached_files(self, expense):
        return list(self.db.files.get(expense.id, []))

    def attach_receipt(self, expense, path):
        self.db.files.setdefault(expense.id, []).append(os.path.basename(path))

    def discover(self):
        print(f"memory target, project {self.project}")


@registry.register
class BasicMemoryTarget(MemoryTarget):
    """A target that only takes time, to test unsupported capabilities."""
    type = "memory-basic"
    display_name = "Basic"
    supports_expenses = False
    supports_receipts = False
    split_by_month = False


def target_cfg(name="client", project="P1", source_projects=(1000001,), type_="memory", **extra):
    t = {"name": name, "type": type_, "source_project_ids": list(source_projects),
         "settings": {"project": project},
         "time_map": [{"source_activity_id": 1001, "code": "T"}],
         "expense_map": {"default": {"code": "E"}}}
    t.update(extra)
    return t


def cfg(*targets, **top):
    c = {"version": 2, "source": {"name": "Kleer"}, "targets": list(targets) or [target_cfg()]}
    c.update(top)
    return c


def week(**changes):
    w = copy.deepcopy(WEEK)
    w.update(changes)
    return w


def expense(id_="5-1", date="2026-10-07", project=1000001, has_receipt=False, path=None, **extra):
    x = {"id": id_, "date": date, "description": "Taxi to client", "amount_ore": 31250,
         "expense_type": "Taxi", "project_id": project, "has_receipt": has_receipt, "receipt_file": path}
    x.update(extra)
    return x


def w40():
    """A week that spans two months: 28 Sep - 4 Oct 2026."""
    ev = lambda i, d, h: {"id": i, "date": d, "hours": h, "activity_id": 1001,  # noqa: E731
                          "project_id": 1000001, "status": "Approved", "comment": ""}
    return {"week": "2026-W40", "from": "2026-09-28", "to": "2026-10-04",
            "time_events": [ev(1, "2026-09-29", 7.0), ev(2, "2026-09-30", 8.0),
                            ev(3, "2026-10-01", 8.0), ev(4, "2026-10-02", 7.0)],
            "expenses": []}


def ops(plans) -> dict:
    """Non-zero action counts over a list of plans, e.g. {"create": 5}."""
    out = {}
    for p in plans:
        for a in p.actions:
            out[a.op] = out.get(a.op, 0) + 1
    return out
