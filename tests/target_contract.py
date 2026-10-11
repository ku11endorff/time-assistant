"""The test suite every target must pass.

Use it in tests/test_target_<type>.py together with a fake of your system's API:

    class MyTargetContract(TargetContract, unittest.TestCase):
        target_type = "mytarget"
        def new_backend(self): ...            # a fresh, empty fake of the API
        def make_target(self, config, backend): ...
        def target_config(self): ...          # see the docstring below
        def add_manual_row(self, backend, config, kind, date): ...
        def other_scope_config(self): ...     # optional

The tests only use the Target interface plus these hooks, so they check behaviour the
engine relies on: creating, safe re-runs, updates, removed entries, rows typed by hand,
date ranges, expenses, receipts, allowances, and targets that share an account.
"""
import copy
import os
import tempfile

from fake_target import WEEK, allowance, expense, ops, w40
from time_assistant import config as conf
from time_assistant import engine


class TargetContract:
    target_type = ""

    # ---- hooks: implement these ----------------------------------------------------------
    def new_backend(self):
        """A fresh, empty fake of the system's API (or of its storage)."""
        raise NotImplementedError

    def make_target(self, config, backend):
        """A Target connected to backend. Set write_pause = 0 to keep the tests fast."""
        raise NotImplementedError

    def target_config(self):
        """A valid config entry for one target: name "client", source_project_ids [1000001],
        a time_map entry for source activity 1001 and an expense_map "default" entry."""
        raise NotImplementedError

    def add_manual_row(self, backend, config, kind, date):
        """Put a row typed by hand (no tag) into backend, in the target's own project."""
        raise NotImplementedError

    def other_scope_config(self):
        """A second target in the same account but another project, or None to skip."""
        return None

    # ---- helpers ----------------------------------------------------------------------------
    def setUp(self):
        self.config = self.target_config()
        self.backend = self.new_backend()
        self.target = self.make_target(self.config, self.backend)
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def sync(self, week, target=None, config=None, apply=True, allow_missing=False):
        config = config or self.config
        target = target or self.target
        cfg = {"version": 2, "source": {"name": "Kleer"}, "targets": [config]}
        plans = engine.plan_target(cfg, config, target, week, allow_missing)
        if apply and not any(p.errors for p in plans):
            for p in plans:
                engine.execute(p, target)
        return plans

    def rows(self, kind, week=WEEK, target=None):
        return (target or self.target).existing(kind, week["from"], week["to"])

    def keys(self, kind, week=WEEK, target=None):
        return {r.key for r in self.rows(kind, week, target) if r.key}

    def needs(self, capability):
        if not getattr(self.target, capability):
            self.skipTest(f"{self.target_type} has no {capability}")

    # ---- the contract -------------------------------------------------------------------------
    def test_config_passes_the_check(self):
        self.assertEqual(conf.check({"version": 2, "targets": [self.target_config()]}), [])

    def test_first_run_creates_every_entry(self):
        plans = self.sync(WEEK)
        self.assertEqual(ops(plans), {"create": 5})
        self.assertEqual(self.keys("time"), {str(e["id"]) for e in WEEK["time_events"]})

    def test_rerun_changes_nothing(self):
        self.sync(WEEK)
        plans = self.sync(WEEK)
        self.assertEqual(ops(plans), {"skip": 5})
        self.assertEqual(len(self.rows("time")), 5)

    def test_changed_hours_update_in_place(self):
        self.sync(WEEK)
        week = copy.deepcopy(WEEK)
        week["time_events"][0]["hours"] = 6.25
        self.assertEqual(ops(self.sync(week)), {"update": 1, "skip": 4})
        self.assertEqual(len(self.rows("time")), 5)
        self.assertEqual(ops(self.sync(week)), {"skip": 5})

    def test_changed_comment_updates_in_place(self):
        self.sync(WEEK)
        week = copy.deepcopy(WEEK)
        week["time_events"][1]["comment"] = "Sprint planning"
        self.assertEqual(ops(self.sync(week)), {"update": 1, "skip": 4})
        self.assertEqual(ops(self.sync(week)), {"skip": 5})

    def test_entry_removed_in_source_is_kept_unless_delete_stale(self):
        self.sync(WEEK)
        week = copy.deepcopy(WEEK)
        week["time_events"].pop()
        self.assertEqual(ops(self.sync(week)), {"skip": 4, "warn": 1})
        self.assertEqual(len(self.rows("time")), 5)
        config = dict(self.config, delete_stale=True)
        target = self.make_target(config, self.backend)
        self.assertEqual(ops(self.sync(week, target=target, config=config)), {"skip": 4, "delete": 1})
        self.assertEqual(len(self.rows("time")), 4)

    def test_rows_typed_by_hand_are_never_touched(self):
        self.add_manual_row(self.backend, self.config, "time", WEEK["time_events"][0]["date"])
        config = dict(self.config, delete_stale=True)
        target = self.make_target(config, self.backend)
        plans = self.sync(WEEK, target=target, config=config)
        self.assertEqual(ops(plans), {"create": 5, "warn": 1})   # flagged as a possible double entry
        manual = [r for r in self.rows("time") if not r.key]
        self.assertEqual(len(manual), 1)
        self.assertEqual(ops(self.sync(WEEK, target=target, config=config)), {"skip": 5})

    def test_reads_only_the_requested_dates(self):
        week = w40()
        self.sync(week)
        sept = self.target.existing("time", "2026-09-28", "2026-09-30")
        self.assertEqual({r.key for r in sept}, {"1", "2"})
        self.assertEqual(ops(self.sync(week)), {"skip": 4})

    def test_expenses_create_and_rerun(self):
        self.needs("supports_expenses")
        week = copy.deepcopy(WEEK)
        week["expenses"] = [expense()]
        self.assertEqual(ops(self.sync(week)), {"create": 6})
        self.assertEqual(self.keys("expense"), {"5-1"})
        self.assertEqual(ops(self.sync(week)), {"skip": 6})
        week["expenses"][0]["amount_ore"] = 20000
        self.assertEqual(ops(self.sync(week)), {"update": 1, "skip": 5})

    def test_receipt_is_attached_once(self):
        self.needs("supports_receipts")
        path = os.path.join(self.tmp.name, "taxi-2026-10-07.pdf")
        with open(path, "wb") as f:
            f.write(b"%PDF-1.4 fake")
        week = copy.deepcopy(WEEK)
        week["expenses"] = [expense(has_receipt=True, path=path)]
        self.assertEqual(ops(self.sync(week)), {"create": 6, "receipt": 1})
        row = self.rows("expense")[0]
        self.assertEqual([n.lower() for n in self.target.attached_files(row)], ["taxi-2026-10-07.pdf"])
        self.assertEqual(ops(self.sync(week)), {"skip": 7})      # 5 time + expense + receipt
        self.assertEqual(len(self.target.attached_files(row)), 1)

    def with_allowance_map(self):
        """The target's config with both allowance types mapped like its default expense."""
        default = self.config["expense_map"]["default"]
        return dict(self.config, allowance_map={"domestic": dict(default), "foreign": dict(default)})

    def test_allowances_create_and_rerun(self):
        self.needs("supports_allowances")
        config = self.with_allowance_map()
        target = self.make_target(config, self.backend)
        week = copy.deepcopy(WEEK)
        week["expenses"] = [expense(), allowance("6-1", type_="domestic"),
                            allowance("6-2", date="2026-10-08", type_="foreign")]
        self.assertEqual(ops(self.sync(week, target=target, config=config)), {"create": 8})
        self.assertEqual(self.keys("expense", target=target), {"5-1", "6-1", "6-2"})
        self.assertEqual(ops(self.sync(week, target=target, config=config)), {"skip": 8})
        week["expenses"][1]["amount_ore"] = 43500
        self.assertEqual(ops(self.sync(week, target=target, config=config)), {"update": 1, "skip": 7})

    def test_allowances_are_opt_in(self):
        self.needs("supports_allowances")
        week = copy.deepcopy(WEEK)
        week["expenses"] = [allowance()]
        self.assertEqual(ops(self.sync(week)), {"create": 5, "warn": 1})   # no allowance_map
        self.assertEqual(self.keys("expense"), set())

    def test_targets_sharing_an_account_do_not_see_each_others_rows(self):
        other = self.other_scope_config()
        if other is None:
            self.skipTest("no second scope for this target")
        self.assertEqual(conf.check({"version": 2, "targets": [self.config, other]}), [])
        second = self.make_target(other, self.backend)
        self.sync(WEEK)
        plans = self.sync(WEEK, target=second, config=other)
        self.assertEqual(ops(plans), {"create": 5})              # not "skip": separate rows
        self.assertEqual(ops(self.sync(WEEK)), {"skip": 5})      # and no stale warnings either
        self.assertEqual(len(self.rows("time")), 5)
        self.assertEqual(len(self.rows("time", target=second)), 5)
