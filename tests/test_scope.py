import copy
import unittest

import _paths  # noqa: F401  (puts the repo root on sys.path)
import sync
import test_sync
from test_sync import CFG, WEEK, ops


def mixed_week():
    """Rows of the configured project plus rows on other Kleer projects (internal time, other client)."""
    w = copy.deepcopy(WEEK)
    w["time_events"] += [
        {"id": 900001, "date": "2026-10-05", "hours": 1.0, "activity_id": 1002,
         "project_id": 1000002, "status": "Approved", "comment": "internal time"},        # internal time
        {"id": 900002, "date": "2026-10-06", "hours": 2.0, "activity_id": 1001,
         "project_id": 777, "status": "Approved", "comment": "other client"},
        {"id": 900003, "date": "2026-10-07", "hours": 0.5, "activity_id": 1001,
         "project_id": None, "status": "Approved", "comment": "no project"},
    ]
    w["expenses"] = [
        {"id": "7-1", "date": "2026-10-07", "description": "Taxi", "amount_ore": 10000,
         "expense_type": "Taxi", "project_id": 1000001, "has_receipt": False},
        {"id": "8-1", "date": "2026-10-07", "description": "Other client lunch", "amount_ore": 9900,
         "expense_type": "Lunch", "project_id": 777, "has_receipt": True},   # no file: must not matter
        {"id": "9-1", "date": "2026-10-08", "description": "No project", "amount_ore": 5000,
         "expense_type": "Misc", "project_id": None, "has_receipt": False},
    ]
    return w


class ScopeTests(unittest.TestCase):
    def run_sync(self, tk, week, cfg=CFG):
        plan = sync.build_plan(cfg, week, tk)
        if not plan.errors:
            sync.execute(plan, tk)
        return plan

    def test_only_project_in_scope_is_replicated(self):
        tk = test_sync.FakeTK()
        plan = self.run_sync(tk, mixed_week())
        self.assertEqual(plan.errors, [])
        self.assertEqual(ops(plan), {"create": 6})          # 5 time + 1 expense
        self.assertEqual(len(tk.time), 5)
        self.assertEqual(len(tk.exp), 1)
        self.assertEqual(len(plan.ignored), 5)               # 3 time + 2 expenses
        for r in tk.time + tk.exp:
            self.assertEqual(r["projectID"], 5001)           # always the TimeKeeper project
            self.assertNotIn("kleer:t:90000", r["comment"])
            self.assertNotIn("kleer:e:8-1", r["comment"])

    def test_nothing_in_scope_writes_nothing(self):
        tk = test_sync.FakeTK()
        week = mixed_week()
        week["time_events"] = [e for e in week["time_events"] if e["project_id"] != 1000001]
        week["expenses"] = [x for x in week["expenses"] if x["project_id"] != 1000001]
        plan = self.run_sync(tk, week)
        self.assertEqual(plan.actions, [])
        self.assertEqual((tk.time, tk.exp), ([], []))

    def test_event_moved_out_of_scope_is_not_silently_deleted(self):
        tk = test_sync.FakeTK()
        self.run_sync(tk, mixed_week())
        week = mixed_week()
        week["time_events"][0]["project_id"] = 1000002         # moved to internal time in Kleer
        plan = self.run_sync(tk, week)
        self.assertEqual(ops(plan)["warn"], 1)                # kept + flagged (delete_stale=false)
        self.assertEqual(len(tk.time), 5)

    def test_scope_config_is_required(self):
        cfg = dict(CFG)
        del cfg["scope"]
        with self.assertRaises(SystemExit):
            sync.build_plan(cfg, mixed_week(), test_sync.FakeTK())


if __name__ == "__main__":
    unittest.main(verbosity=2)
