import copy, json, unittest
import _paths  # noqa: F401  (puts the repo root on sys.path)
import sync
from test_sync import FakeTK, CFG  # reuse fixtures

class ApprovalTests(unittest.TestCase):
    def week(self):
        return json.load(open(_paths.EXAMPLE_WEEK))

    def test_approved_week_plans_normally(self):
        p = sync.build_plan(copy.deepcopy(CFG), self.week(), FakeTK())
        self.assertEqual(p.errors, [])
        self.assertEqual(len([a for a in p.actions if a.op == "create"]), 5)

    def test_certified_counts_as_approved(self):
        w = self.week()
        for e in w["time_events"]: e["status"] = "Certified"
        self.assertEqual(sync.build_plan(copy.deepcopy(CFG), w, FakeTK()).errors, [])

    def test_open_event_blocks_whole_week(self):
        w = self.week(); w["time_events"][2]["status"] = "Open"
        p = sync.build_plan(copy.deepcopy(CFG), w, FakeTK())
        self.assertIn("not yet been approved in Kleer", p.errors[0])
        self.assertIn("2026-10-07", p.errors[0])
        self.assertEqual(p.actions, [])

    def test_missing_status_fails_closed(self):
        w = self.week(); del w["time_events"][0]["status"]
        p = sync.build_plan(copy.deepcopy(CFG), w, FakeTK())
        self.assertTrue(p.errors)

    def test_unapproved_other_project_also_blocks(self):
        w = self.week()
        w["time_events"].append({"id": 1, "date": "2026-10-09", "hours": 1, "activity_id": 5,
                                 "project_id": 999, "status": "Open", "comment": ""})
        self.assertTrue(sync.build_plan(copy.deepcopy(CFG), w, FakeTK()).errors)

if __name__ == "__main__":
    unittest.main()
