"""The target-independent engine, tested with in-memory targets."""
import contextlib
import copy
import io
import os
import tempfile
import unittest

import _paths  # noqa: F401  (puts the repo root on sys.path)
from fake_target import (WEEK, MemoryBackend, MemoryTarget, cfg, expense, ops, target_cfg,
                         w40, week)
from target_contract import TargetContract
from time_assistant import engine
from time_assistant import targets as registry


class MemoryContract(TargetContract, unittest.TestCase):
    """The contract suite run against the in-memory target (proves the suite itself)."""
    target_type = "memory"

    def new_backend(self):
        return MemoryBackend()

    def make_target(self, config, backend):
        return MemoryTarget(config, backend=backend)

    def target_config(self):
        return target_cfg()

    def add_manual_row(self, backend, config, kind, date):
        backend.next_id += 1
        backend.rows[kind].append({"id": backend.next_id, "date": date, "project": config["settings"]["project"],
                                   "code": "X", "value": 1, "comment": "typed by hand"})

    def other_scope_config(self):
        return target_cfg(name="other", project="P2")


class Harness:
    """Runs engine.run with one backend per target name and captures the output."""
    def __init__(self):
        self.backends = {}
        self.refuse = set()       # target names whose connect fails

    def connect(self, tcfg):
        if tcfg["name"] in self.refuse:
            raise SystemExit("No password found for target")
        cls = registry.get(tcfg["type"])
        return cls(tcfg, backend=self.backends.setdefault(tcfg["name"], MemoryBackend()))

    def rows(self, name, kind="time"):
        return self.backends.get(name, MemoryBackend()).rows[kind]

    def run(self, config, wk, apply=True, names=None, allow_missing=False):
        out, code = io.StringIO(), 0
        with contextlib.redirect_stdout(out):
            try:
                code = engine.run(config, wk, self.connect, names=names, apply=apply,
                                  allow_missing_receipts=allow_missing)
            except SystemExit as e:
                code = e.code if isinstance(e.code, int) else 1
                print(e.code)
        return out.getvalue(), code


class ApprovalTests(unittest.TestCase):
    def test_approved_week_is_written(self):
        h = Harness()
        out, code = h.run(cfg(), week())
        self.assertEqual(code, 0)
        self.assertEqual(len(h.rows("client")), 5)

    def test_certified_counts_as_approved(self):
        w = week()
        for e in w["time_events"]:
            e["status"] = "Certified"
        self.assertEqual(engine.approval_errors(cfg(), w), [])

    def test_open_entry_blocks_every_target(self):
        h = Harness()
        w = week()
        w["time_events"][2]["status"] = "Open"
        two = cfg(target_cfg(), target_cfg(name="partner", project="P9"))
        out, code = h.run(two, w)
        self.assertNotEqual(code, 0)
        self.assertIn("has not yet been approved in Kleer", out)
        self.assertIn("2026-10-07", out)
        self.assertEqual((h.rows("client"), h.rows("partner")), ([], []))

    def test_default_rerun_hint_is_generic(self):
        w = week()
        w["time_events"][0]["status"] = "Open"
        self.assertTrue(engine.approval_errors(cfg(), w)[0].endswith("then run the export again."))

    def test_custom_rerun_hint(self):
        w = week()
        w["time_events"][0]["status"] = "Open"
        c = cfg(source={"name": "Kleer", "rerun_hint": "ask Claude to run the time-assistant skill again."})
        self.assertTrue(engine.approval_errors(c, w)[0].endswith(
            "then ask Claude to run the time-assistant skill again."))

    def test_source_name_is_used_in_the_message(self):
        w = week()
        w["time_events"][0]["status"] = "Open"
        msg = engine.approval_errors(cfg(source={"name": "Harvest"}), w)[0]
        self.assertIn("WEEK NOT APPROVED IN HARVEST", msg)
        self.assertNotIn("Kleer", msg)

    def test_missing_status_fails_closed(self):
        w = week()
        del w["time_events"][0]["status"]
        self.assertTrue(engine.approval_errors(cfg(), w))

    def test_unapproved_entry_on_another_project_also_blocks(self):
        w = week()
        w["time_events"].append({"id": 1, "date": "2026-10-09", "hours": 1, "activity_id": 5,
                                 "project_id": 999, "status": "Open", "comment": ""})
        self.assertTrue(engine.approval_errors(cfg(), w))

    def test_custom_accepted_statuses_and_opt_out(self):
        w = week()
        for e in w["time_events"]:
            e["status"] = "Signed off"
        self.assertEqual(engine.approval_errors(cfg(approval={"accepted_statuses": ["Signed off"]}), w), [])
        self.assertTrue(engine.approval_errors(cfg(), w))
        self.assertEqual(engine.approval_errors(cfg(approval={"required": False}), w), [])

    def test_target_that_only_takes_certified_blocks_apply_but_others_can_run_alone(self):
        h = Harness()
        two = cfg(target_cfg(), target_cfg(name="partner", project="P9", accepted_statuses=["Certified"]))
        out, code = h.run(two, week())
        self.assertNotEqual(code, 0)
        self.assertIn("only takes entries with status Certified", out)
        self.assertIn("--target client", out)
        self.assertEqual(h.rows("client"), [])                      # errors anywhere: nothing written
        out, code = h.run(two, week(), names=["client"])
        self.assertEqual(code, 0)
        self.assertEqual((len(h.rows("client")), h.rows("partner")), (5, []))


class RoutingTests(unittest.TestCase):
    def mixed_week(self):
        w = week()
        w["time_events"] += [
            {"id": 900001, "date": "2026-10-05", "hours": 1.0, "activity_id": 1001,
             "project_id": 1000002, "status": "Approved", "comment": "internal time"},
            {"id": 900002, "date": "2026-10-06", "hours": 2.0, "activity_id": 1001,
             "project_id": 777, "status": "Approved", "comment": "other client"},
            {"id": 900003, "date": "2026-10-07", "hours": 0.5, "activity_id": 1001,
             "project_id": None, "status": "Approved", "comment": "no project"},
        ]
        w["expenses"] = [expense("7-1"), expense("8-1", project=777, has_receipt=True),
                         expense("9-1", project=None)]
        return w

    def test_entries_outside_every_target_are_listed_and_need_nothing(self):
        h = Harness()
        out, code = h.run(cfg(), self.mixed_week())   # 8-1 has a receipt but no file: must not matter
        self.assertEqual(code, 0, out)
        self.assertEqual((len(h.rows("client")), len(h.rows("client", "expense"))), (5, 1))
        self.assertIn("Not replicated to any target (5 items", out)
        for r in h.rows("client") + h.rows("client", "expense"):
            self.assertEqual(r["project"], "P1")

    def test_each_target_gets_only_its_projects(self):
        h = Harness()
        two = cfg(target_cfg(), target_cfg(name="other", project="P7", source_projects=[777]))
        w = self.mixed_week()
        w["expenses"][1]["has_receipt"] = False
        out, code = h.run(two, w)
        self.assertEqual(code, 0, out)
        self.assertEqual(len(h.rows("client")), 5)
        self.assertEqual(len(h.rows("client", "expense")), 1)
        self.assertEqual([r["comment"] for r in h.rows("other")], ["other client [ta:t:900002]"])
        self.assertEqual(len(h.rows("other", "expense")), 1)
        self.assertIn("Not replicated to any target (3 items", out)   # 900001, 900003, 9-1

    def test_the_same_project_can_go_to_several_targets(self):
        h = Harness()
        two = cfg(target_cfg(), target_cfg(name="partner", project="P9"))
        out, code = h.run(two, week())
        self.assertEqual(code, 0, out)
        self.assertEqual((len(h.rows("client")), len(h.rows("partner"))), (5, 5))
        self.assertIn("=== client (Memory) ===", out)
        self.assertIn("=== partner (Memory) ===", out)

    def test_entry_moved_to_another_project_is_kept_and_flagged(self):
        h = Harness()
        h.run(cfg(), week())
        w = week()
        w["time_events"][0]["project_id"] = 1000002
        out, code = h.run(cfg(), w)
        self.assertIn("no longer in the source", out)
        self.assertEqual(len(h.rows("client")), 5)

    def test_disabled_target_is_skipped_unless_named(self):
        h = Harness()
        two = cfg(target_cfg(), target_cfg(name="partner", project="P9", enabled=False))
        h.run(two, week())
        self.assertEqual(h.rows("partner"), [])
        h.run(two, week(), names=["partner"])
        self.assertEqual(len(h.rows("partner")), 5)

    def test_unknown_target_name(self):
        out, code = Harness().run(cfg(), week(), names=["nope"])
        self.assertIn("Unknown target(s): nope", out)


class ErrorTests(unittest.TestCase):
    def test_unmapped_activity_blocks_every_target(self):
        h = Harness()
        w = week()
        w["time_events"][2]["activity_id"] = 999
        two = cfg(target_cfg(), target_cfg(name="partner", project="P9",
                                           time_map=[{"code": "D"}]))   # partner has a default entry
        out, code = h.run(two, w)
        self.assertIn("has no mapping in time_map of target 'client'", out)
        self.assertIn("Refusing to apply", out)
        self.assertEqual((h.rows("client"), h.rows("partner")), ([], []))

    def test_target_that_cannot_connect_is_reported_and_others_still_plan(self):
        h = Harness()
        h.refuse.add("partner")
        two = cfg(target_cfg(), target_cfg(name="partner", project="P9"))
        out, code = h.run(two, week(), apply=False)
        self.assertNotEqual(code, 0)
        self.assertIn("cannot connect", out)
        self.assertIn("CREATE  2026-10-05 time #7000001", out)

    def test_dry_run_writes_nothing_and_prints_the_summary_line(self):
        h = Harness()
        out, code = h.run(cfg(), week(), apply=False)
        self.assertEqual(code, 0)
        self.assertEqual(h.rows("client"), [])
        self.assertIn("\ndry run - nothing written: 5 create, 0 update", out)
        h.run(cfg(), week())
        out, _ = h.run(cfg(), week(), apply=False)
        self.assertIn("\ndry run - nothing written: 0 create, 0 update, 0 delete, 0 receipts, 5 unchanged", out)


class MonthSplitTests(unittest.TestCase):
    def test_segments(self):
        segs = engine.split_by_month(w40())
        self.assertEqual([(s["from"], s["to"]) for s in segs],
                         [("2026-09-28", "2026-09-30"), ("2026-10-01", "2026-10-04")])
        self.assertEqual([len(s["time_events"]) for s in segs], [2, 2])

    def test_single_month_week_and_year_end(self):
        w = {"from": "2026-12-28", "to": "2027-01-03", "time_events": [], "expenses": []}
        self.assertEqual([(s["from"], s["to"]) for s in engine.split_by_month(w)],
                         [("2026-12-28", "2026-12-31"), ("2027-01-01", "2027-01-03")])
        w = {"from": "2026-10-05", "to": "2026-10-11", "time_events": [], "expenses": []}
        self.assertEqual(len(engine.split_by_month(w)), 1)

    def test_apply_writes_both_months_and_rerun_is_clean(self):
        h = Harness()
        out, code = h.run(cfg(), w40())
        self.assertEqual(code, 0, out)
        self.assertEqual(len(h.rows("client")), 4)
        self.assertIn("Month 2026-09", out)
        self.assertIn("Month 2026-10", out)
        out, _ = h.run(cfg(), w40(), apply=False)
        self.assertIn("0 create, 0 update, 0 delete, 0 receipts, 4 unchanged", out)

    def test_one_month_failing_does_not_block_the_other(self):
        h = Harness()
        h.backends["client"] = MemoryBackend()
        h.backends["client"].fail = lambda kind, p: p["date"].startswith("2026-09")
        out, code = h.run(cfg(), w40())
        self.assertEqual([r["date"][:7] for r in h.rows("client")], ["2026-10", "2026-10"])
        self.assertIn("FAILED  client month 2026-09", out)
        self.assertNotEqual(code, 0)

    def test_one_target_failing_does_not_block_the_other(self):
        h = Harness()
        h.backends["client"] = MemoryBackend()
        h.backends["client"].fail = lambda kind, p: True
        two = cfg(target_cfg(), target_cfg(name="partner", project="P9"))
        out, code = h.run(two, week())
        self.assertNotEqual(code, 0)
        self.assertIn("Not fully written: client", out)
        self.assertEqual(len(h.rows("partner")), 5)

    def test_target_without_month_split_gets_one_period(self):
        h = Harness()
        out, code = h.run(cfg(target_cfg(type_="memory-basic")), w40())
        self.assertEqual(code, 0, out)
        self.assertNotIn("Month 2026-09", out)
        self.assertEqual(len(h.rows("client")), 4)


class CapabilityTests(unittest.TestCase):
    def test_target_without_expense_map_lists_expenses_instead_of_failing(self):
        h = Harness()
        two = cfg(target_cfg(), target_cfg(name="partner", project="P9", expense_map={}))
        out, code = h.run(two, week(expenses=[expense()]))
        self.assertEqual(code, 0, out)
        self.assertIn("expense #5-1 not replicated: target 'partner' has no expense_map", out)
        self.assertEqual((len(h.rows("client", "expense")), h.rows("partner", "expense")), (1, []))
        self.assertEqual(len(h.rows("partner")), 5)

    def test_expenses_are_reported_when_a_target_does_not_take_them(self):
        h = Harness()
        out, code = h.run(cfg(target_cfg(type_="memory-basic")), week(expenses=[expense()]))
        self.assertEqual(code, 0, out)
        self.assertIn("expense #5-1 not replicated: Basic does not take expenses", out)
        self.assertEqual(len(h.rows("client")), 5)


class ReceiptTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.dir.name, "taxi.pdf")
        with open(self.path, "wb") as f:
            f.write(b"%PDF-1.4 fake")

    def tearDown(self):
        self.dir.cleanup()

    def test_missing_receipt_blocks_apply(self):
        h = Harness()
        out, code = h.run(cfg(), week(expenses=[expense(has_receipt=True)]))
        self.assertIn("no receipt_file was given", out)
        self.assertEqual((h.rows("client"), h.rows("client", "expense")), ([], []))

    def test_missing_receipt_can_be_allowed(self):
        h = Harness()
        out, code = h.run(cfg(), week(expenses=[expense(has_receipt=True)]), allow_missing=True)
        self.assertEqual(code, 0, out)
        self.assertEqual(len(h.rows("client", "expense")), 1)
        self.assertEqual(h.backends["client"].files, {})

    def test_file_not_found_and_icloud_placeholder_hint(self):
        ghost = os.path.join(self.dir.name, "lunch.pdf")
        open(os.path.join(self.dir.name, ".lunch.pdf.icloud"), "w").close()
        out, _ = Harness().run(cfg(), week(expenses=[expense(has_receipt=True, path=ghost)]))
        self.assertIn("not downloaded", out)

    def test_expense_without_receipt_needs_no_file(self):
        h = Harness()
        out, code = h.run(cfg(), week(expenses=[expense()]))
        self.assertEqual(code, 0, out)
        self.assertEqual(len(h.rows("client", "expense")), 1)

    def test_receipt_on_an_existing_expense_is_added_later(self):
        h = Harness()
        h.run(cfg(), week(expenses=[expense()]))
        out, code = h.run(cfg(), week(expenses=[expense(has_receipt=True, path=self.path)]))
        self.assertEqual(code, 0, out)
        self.assertEqual(list(h.backends["client"].files.values()), [["taxi.pdf"]])


class MappingTests(unittest.TestCase):
    def test_specific_activity_wins_over_default(self):
        t = target_cfg(time_map=[{"code": "D"}, {"source_activity_id": 1001, "code": "S"}])
        self.assertEqual(engine.time_mapping(t, {"activity_id": 1001})["code"], "S")
        self.assertEqual(engine.time_mapping(t, {"activity_id": 5})["code"], "D")

    def test_expense_type_wins_over_default(self):
        t = target_cfg(expense_map={"default": {"code": "D"}, "Taxi": {"code": "TX"}})
        self.assertEqual(engine.expense_mapping(t, {"expense_type": "Taxi"})["code"], "TX")
        self.assertEqual(engine.expense_mapping(t, {"expense_type": "Hotel"})["code"], "D")

    def test_comment_falls_back_to_mapping_comment(self):
        h = Harness()
        t = target_cfg(time_map=[{"source_activity_id": 1001, "code": "T", "comment": "Consulting"}])
        w = copy.deepcopy(WEEK)
        w["time_events"][0]["comment"] = "Planning"
        h.run(cfg(t), w)
        comments = sorted(r["comment"] for r in h.rows("client"))
        self.assertIn("Planning [ta:t:7000001]", comments)
        self.assertIn("Consulting [ta:t:7000002]", comments)


if __name__ == "__main__":
    unittest.main()
