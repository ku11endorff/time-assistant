import copy
import os
import tempfile
import unittest

import _paths  # noqa: F401  (puts the repo root on sys.path)
import sync
import test_sync
from test_sync import CFG, WEEK, ops


class FakeTK2(test_sync.FakeTK):
    def __init__(self):
        super().__init__()
        self.files = {}  # expense id -> [file names]

    def expense_files(self, eid):
        return [{"fileName": n} for n in self.files.get(eid, [])]

    def upload_expense_file(self, eid, path):
        self.files.setdefault(eid, []).append(os.path.basename(path))


def week_with_expense(path=None, has_receipt=True):
    week = copy.deepcopy(WEEK)
    week["expenses"] = [{"id": "5-1", "date": "2026-10-07", "description": "Taxi to client",
                         "amount_ore": 31250, "expense_type": "Taxi",
                         "project_id": 1000001,
                         "has_receipt": has_receipt, "receipt_file": path}]
    return week


def run(tk, week, allow_missing=False):
    plan = sync.build_plan(CFG, week, tk, allow_missing_receipts=allow_missing)
    if not plan.errors:
        sync.execute(plan, tk)
    return plan


class CommentTests(unittest.TestCase):
    def test_external_comment_is_used_and_edits_propagate(self):
        tk = FakeTK2()
        week = copy.deepcopy(WEEK)
        week["time_events"][0]["comment"] = "Sprint planning and migration work"
        run(tk, week)
        row = next(r for r in tk.time if r["date"] == "2026-10-05")
        self.assertEqual(row["comment"], "Sprint planning and migration work [kleer:t:7000001]")
        # empty comment elsewhere -> marker only
        other = next(r for r in tk.time if r["date"] == "2026-10-06")
        self.assertEqual(other["comment"], "[kleer:t:7000002]")
        # edit comment in Kleer -> update in place
        week["time_events"][0]["comment"] = "Sprint planning"
        plan = run(tk, week)
        self.assertEqual(ops(plan), {"update": 1, "skip": 4})
        self.assertEqual(len(tk.time), 5)
        row = next(r for r in tk.time if r["date"] == "2026-10-05")
        self.assertEqual(row["comment"], "Sprint planning [kleer:t:7000001]")


class ReceiptTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.dir.name, "taxi-2026-10-07.pdf")
        with open(self.path, "wb") as f:
            f.write(b"%PDF-1.4 fake")

    def tearDown(self):
        self.dir.cleanup()

    def test_receipt_uploaded_after_create_and_not_repeated(self):
        tk = FakeTK2()
        plan = run(tk, week_with_expense(self.path))
        self.assertEqual(ops(plan), {"create": 6, "receipt": 1})
        eid = tk.exp[0]["id"]
        self.assertEqual(tk.files[eid], ["taxi-2026-10-07.pdf"])
        plan = run(tk, week_with_expense(self.path))
        self.assertEqual(ops(plan), {"skip": 7})  # 5 time + 1 expense + 1 receipt
        self.assertEqual(tk.files[eid], ["taxi-2026-10-07.pdf"])  # no second upload

    def test_missing_receipt_blocks_apply(self):
        tk = FakeTK2()
        plan = run(tk, week_with_expense(None))
        self.assertEqual(len(plan.errors), 1)
        self.assertEqual((tk.time, tk.exp), ([], []))  # nothing written at all

    def test_missing_receipt_can_be_allowed(self):
        tk = FakeTK2()
        plan = run(tk, week_with_expense(None), allow_missing=True)
        self.assertEqual(plan.errors, [])
        self.assertEqual(len(tk.exp), 1)
        self.assertEqual(tk.files, {})

    def test_file_not_found_and_icloud_placeholder_hint(self):
        tk = FakeTK2()
        ghost = os.path.join(self.dir.name, "lunch.pdf")
        open(os.path.join(self.dir.name, ".lunch.pdf.icloud"), "w").close()
        plan = run(tk, week_with_expense(ghost))
        self.assertEqual(len(plan.errors), 1)
        self.assertIn("not downloaded", plan.errors[0])

    def test_expense_without_receipt_needs_no_file(self):
        tk = FakeTK2()
        plan = run(tk, week_with_expense(None, has_receipt=False))
        self.assertEqual(ops(plan), {"create": 6})


if __name__ == "__main__":
    unittest.main(verbosity=2)
