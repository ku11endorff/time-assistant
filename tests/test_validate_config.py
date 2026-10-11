import copy
import json
import os
import tempfile
import unittest

import _paths  # noqa: F401  (puts the repo root on sys.path)
import sync
from test_sync import CFG, FakeTK

WEEK = json.load(open(_paths.EXAMPLE_WEEK))


class ValidateTests(unittest.TestCase):
    def test_example_is_valid(self):
        self.assertEqual(sync.validate_week(WEEK), [])

    def test_catches_typical_agent_mistakes(self):
        w = copy.deepcopy(WEEK)
        w["time_events"][0]["hours"] = "7.5"          # string instead of number
        w["time_events"][1]["date"] = "2026-11-01"    # outside the week
        w["time_events"][2]["id"] = w["time_events"][3]["id"]   # duplicate
        del w["time_events"][4]["status"]
        errs = " | ".join(sync.validate_week(w))
        for needle in ("hours", "outside from/to", "duplicate id", "status"):
            self.assertIn(needle, errs)

    def test_expense_amount_must_be_integer_minor_units(self):
        w = copy.deepcopy(WEEK)
        w["expenses"] = [{"id": "1-1", "date": "2026-10-06", "amount_ore": 312.5,
                          "project_id": None, "has_receipt": False}]
        self.assertTrue(any("amount_ore" in e for e in sync.validate_week(w)))

    def test_cli_validate_and_invalid_file_blocks_plan(self):
        with tempfile.TemporaryDirectory() as d:
            bad = os.path.join(d, "bad.json")
            json.dump({"from": "x"}, open(bad, "w"))
            with self.assertRaises(SystemExit):
                sync.main(["validate", "--week", bad])
            cfgp = os.path.join(d, "c.json")
            json.dump(CFG, open(cfgp, "w"))
            with self.assertRaises(SystemExit):
                sync.main(["--config", cfgp, "plan", "--week", bad])


class ApprovalConfigTests(unittest.TestCase):
    def week(self, status):
        w = copy.deepcopy(WEEK)
        for e in w["time_events"]:
            e["status"] = status
        return w

    def test_custom_accepted_statuses(self):
        cfg = copy.deepcopy(CFG)
        cfg["approval"] = {"accepted_statuses": ["Signed off"]}
        self.assertEqual(sync.build_plan(cfg, self.week("Signed off"), FakeTK()).errors, [])
        self.assertTrue(sync.build_plan(cfg, self.week("Approved"), FakeTK()).errors)

    def test_gate_can_be_disabled_explicitly(self):
        cfg = copy.deepcopy(CFG)
        cfg["approval"] = {"required": False}
        self.assertEqual(sync.build_plan(cfg, self.week("Open"), FakeTK()).errors, [])

    def test_default_blocks_open(self):
        self.assertTrue(sync.build_plan(copy.deepcopy(CFG), self.week("Open"), FakeTK()).errors)


if __name__ == "__main__":
    unittest.main()
