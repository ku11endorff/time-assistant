import copy
import json
import unittest

import _paths  # noqa: F401  (puts the repo root on sys.path)
import sync

CFG = {
    "timekeeper_user_id": 7,
    "delete_stale": False,
    "scope": {"kleer_project_nr": "100", "kleer_project_id": 1000001, "tk_project_id": 5001},
    "time_map": [{"kleer_activity_id": 1001, "tk_activity_id": 22, "tk_timecode_id": 33}],
    "expense_map": {"default": {"tk_wagecode_id": 44}},
}
WEEK = json.load(open(_paths.EXAMPLE_WEEK))


class FakeTK:
    """In-memory stand-in for the TimeKeeper client."""
    def __init__(self):
        self.time, self.exp, self.next_id = [], [], 1000

    def time_regs(self, *_):   return [dict(r) for r in self.time]
    def expense_regs(self, *_): return [dict(r) for r in self.exp]

    def _add(self, store, body):
        self.next_id += 1
        store.append(dict(body, id=self.next_id))

    def create_time(self, b): self._add(self.time, b)
    def create_exp(self, b):  self._add(self.exp, b)

    def update_time(self, b):
        self.time[:] = [dict(b) if r["id"] == b["id"] else r for r in self.time]

    def update_exp(self, b):
        self.exp[:] = [dict(b) if r["id"] == b["id"] else r for r in self.exp]

    def delete_time(self, i): self.time[:] = [r for r in self.time if r["id"] != i]
    def delete_exp(self, i):  self.exp[:] = [r for r in self.exp if r["id"] != i]


def ops(plan):
    out = {}
    for a in plan.actions:
        out[a.op] = out.get(a.op, 0) + 1
    return out


class SyncTests(unittest.TestCase):
    def run_sync(self, tk, cfg=CFG, week=WEEK):
        plan = sync.build_plan(cfg, week, tk)
        if not plan.errors:
            sync.execute(plan, tk)
        return plan

    def test_first_run_creates_all_and_converts_hours(self):
        tk = FakeTK()
        plan = self.run_sync(tk)
        self.assertEqual(ops(plan), {"create": 5})
        by_date = {r["date"]: r for r in tk.time}
        self.assertEqual((by_date["2026-10-05"]["hours"], by_date["2026-10-05"]["minutes"]), (7, 30))
        self.assertEqual((by_date["2026-10-06"]["hours"], by_date["2026-10-06"]["minutes"]), (8, 30))
        self.assertIn("[kleer:t:7000001]", by_date["2026-10-05"]["comment"])
        self.assertEqual(sum(r["hours"] * 60 + r["minutes"] for r in tk.time), 39 * 60)

    def test_rerun_is_idempotent(self):
        tk = FakeTK()
        self.run_sync(tk)
        plan = self.run_sync(tk)
        self.assertEqual(ops(plan), {"skip": 5})
        self.assertEqual(len(tk.time), 5)

    def test_changed_hours_updates_in_place(self):
        tk = FakeTK()
        self.run_sync(tk)
        week = copy.deepcopy(WEEK)
        week["time_events"][0]["hours"] = 6.25
        plan = self.run_sync(tk, week=week)
        self.assertEqual(ops(plan), {"update": 1, "skip": 4})
        self.assertEqual(len(tk.time), 5)
        row = next(r for r in tk.time if r["date"] == "2026-10-05")
        self.assertEqual((row["hours"], row["minutes"]), (6, 15))

    def test_removed_in_kleer_is_kept_unless_delete_stale(self):
        tk = FakeTK()
        self.run_sync(tk)
        week = copy.deepcopy(WEEK)
        week["time_events"].pop()
        plan = self.run_sync(tk, week=week)
        self.assertEqual(ops(plan), {"skip": 4, "warn": 1})
        self.assertEqual(len(tk.time), 5)
        plan = self.run_sync(tk, cfg=dict(CFG, delete_stale=True), week=week)
        self.assertEqual(ops(plan), {"skip": 4, "delete": 1})
        self.assertEqual(len(tk.time), 4)

    def test_manual_rows_are_never_touched_but_flagged(self):
        tk = FakeTK()
        tk.time.append({"id": 1, "date": "2026-10-05T00:00:00", "hours": 7, "minutes": 30,
                        "projectID": 5001, "activityID": 22, "timeCodeID": 33,
                        "comment": "typed by hand"})
        plan = self.run_sync(tk, cfg=dict(CFG, delete_stale=True))
        self.assertEqual(ops(plan)["warn"], 1)
        self.assertTrue(any(r["id"] == 1 for r in tk.time))
        self.assertEqual(len(tk.time), 6)

    def test_unmapped_activity_blocks_everything(self):
        tk = FakeTK()
        week = copy.deepcopy(WEEK)
        week["time_events"][2]["activity_id"] = 999
        plan = self.run_sync(tk, week=week)
        self.assertEqual(len(plan.errors), 1)
        self.assertEqual(tk.time, [])  # nothing written

    def test_expenses_create_and_rerun(self):
        tk = FakeTK()
        week = copy.deepcopy(WEEK)
        week["expenses"] = [{"id": "5-1", "date": "2026-10-07", "description": "Taxi",
                             "amount_ore": 31250, "expense_type": "Taxi",
                             "project_id": 1000001}]
        plan = self.run_sync(tk, week=week)
        self.assertEqual(ops(plan), {"create": 6})
        self.assertEqual(tk.exp[0]["price"], 312.5)
        self.assertEqual(tk.exp[0]["comment"], "Taxi [kleer:e:5-1]")
        plan = self.run_sync(tk, week=week)
        self.assertEqual(ops(plan), {"skip": 6})

    def test_response_envelope_variants(self):
        self.assertEqual(sync.extract_items([{"a": 1}]), [{"a": 1}])
        self.assertEqual(sync.extract_items({"Data": [{"a": 1}]}), [{"a": 1}])
        self.assertEqual(sync.extract_items({"data": {"items": [{"a": 1}]}}), [{"a": 1}])
        self.assertEqual(sync.extract_items(None), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
