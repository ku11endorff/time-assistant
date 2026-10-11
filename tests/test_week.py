import copy
import unittest

import _paths  # noqa: F401  (puts the repo root on sys.path)
from fake_target import WEEK
from time_assistant.week import validate_week


class ValidateTests(unittest.TestCase):
    def test_example_is_valid(self):
        self.assertEqual(validate_week(WEEK), [])

    def test_catches_typical_agent_mistakes(self):
        w = copy.deepcopy(WEEK)
        w["time_events"][0]["hours"] = "7.5"                    # string instead of number
        w["time_events"][1]["date"] = "2026-11-01"              # outside the week
        w["time_events"][2]["id"] = w["time_events"][3]["id"]   # duplicate
        del w["time_events"][4]["status"]
        errs = " | ".join(validate_week(w))
        for needle in ("hours", "outside from/to", "duplicate id", "status"):
            self.assertIn(needle, errs)

    def test_ids_must_fit_in_a_row_tag(self):
        w = copy.deepcopy(WEEK)
        w["time_events"][0]["id"] = "7000001 a"
        w["time_events"][1]["id"] = "x:1"
        errs = [e for e in validate_week(w) if "'id' may only contain" in e]
        self.assertEqual(len(errs), 2)

    def test_expense_amount_must_be_integer_minor_units(self):
        w = copy.deepcopy(WEEK)
        w["expenses"] = [{"id": "1-1", "date": "2026-10-06", "amount_ore": 312.5,
                          "project_id": None, "has_receipt": False}]
        self.assertTrue(any("amount_ore" in e for e in validate_week(w)))

    def test_allowances(self):
        ok = {"id": "6-1", "kind": "allowance", "allowance_type": "foreign", "date": "2026-10-06",
              "amount_ore": 58000, "project_id": 1000001, "has_receipt": False}
        w = copy.deepcopy(WEEK)
        w["expenses"] = [ok]
        self.assertEqual(validate_week(w), [])
        w["expenses"] = [dict(ok, id="6-2", allowance_type="abroad"),
                         dict(ok, id="6-3", has_receipt=True),
                         dict(ok, id="6-4", kind="mileage")]
        errs = " | ".join(validate_week(w))
        for needle in ("'allowance_type' \"domestic\"", "an allowance has no receipt", "'kind' must be"):
            self.assertIn(needle, errs)

    def test_shape_errors(self):
        self.assertEqual(validate_week([]), ["week file must be a JSON object"])
        errs = " | ".join(validate_week({"from": "x"}))
        for needle in ("'from' must be a date", "'time_events' must be a list", "'expenses' must be a list"):
            self.assertIn(needle, errs)


if __name__ == "__main__":
    unittest.main()
