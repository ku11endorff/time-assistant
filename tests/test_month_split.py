import contextlib, io, json, os, tempfile, unittest
from unittest import mock

import _paths  # noqa: F401  (puts the repo root on sys.path)
import sync
from test_sync import CFG, FakeTK


class DatedTK(FakeTK):
    """FakeTK that honours the date range, like the real API."""
    def time_regs(self, uid, d_from, d_to):
        return [dict(r) for r in self.time if d_from <= r["date"][:10] <= d_to]

    def expense_regs(self, uid, d_from, d_to):
        return [dict(r) for r in self.exp if d_from <= r["date"][:10] <= d_to]


def w40():
    ev = lambda i, d, h: {"id": i, "date": d, "hours": h, "activity_id": 1001,
                          "project_id": 1000001, "status": "Approved", "comment": ""}
    return {"week": "2026-W40", "from": "2026-09-28", "to": "2026-10-04",
            "time_events": [ev(1, "2026-09-29", 7.0), ev(2, "2026-09-30", 8.0),
                            ev(3, "2026-10-01", 8.0), ev(4, "2026-10-02", 7.0)],
            "expenses": []}


def run(week, tk, apply, cfg=CFG):
    with tempfile.TemporaryDirectory() as d:
        cp, wp = os.path.join(d, "c.json"), os.path.join(d, "w.json")
        json.dump(cfg, open(cp, "w")); json.dump(week, open(wp, "w"))
        out = io.StringIO()
        code = 0
        with mock.patch.object(sync, "make_client", return_value=tk), contextlib.redirect_stdout(out):
            try:
                sync.main(["--config", cp, "apply" if apply else "plan", "--week", wp])
            except SystemExit as e:
                code = e.code or 0
        return out.getvalue(), code


class MonthSplitTests(unittest.TestCase):
    def test_segments(self):
        segs = sync.split_by_month(w40())
        self.assertEqual([(s["from"], s["to"]) for s in segs],
                         [("2026-09-28", "2026-09-30"), ("2026-10-01", "2026-10-04")])
        self.assertEqual([len(s["time_events"]) for s in segs], [2, 2])

    def test_single_month_week_is_one_segment_and_year_end_works(self):
        w = {"from": "2026-12-28", "to": "2027-01-03", "time_events": [], "expenses": []}
        self.assertEqual([(s["from"], s["to"]) for s in sync.split_by_month(w)],
                         [("2026-12-28", "2026-12-31"), ("2027-01-01", "2027-01-03")])
        w = {"from": "2026-10-05", "to": "2026-10-11", "time_events": [], "expenses": []}
        self.assertEqual(len(sync.split_by_month(w)), 1)

    def test_apply_posts_both_months_and_rerun_is_clean(self):
        tk = DatedTK()
        out, code = run(w40(), tk, apply=True)
        self.assertEqual(code, 0)
        self.assertEqual(len(tk.time), 4)
        self.assertIn("Month 2026-09", out); self.assertIn("Month 2026-10", out)
        out, _ = run(w40(), tk, apply=False)
        self.assertIn("0 create, 0 update, 0 delete, 0 receipts, 4 unchanged", out)
        self.assertEqual(len(tk.time), 4)

    def test_one_month_failing_does_not_block_the_other(self):
        class Locked(DatedTK):
            def create_time(self, b):
                if b["date"].startswith("2026-09"):
                    raise SystemExit("HTTP 403: period closed")
                super().create_time(b)
        tk = Locked()
        out, code = run(w40(), tk, apply=True)
        self.assertEqual([r["date"][:7] for r in tk.time], ["2026-10", "2026-10"])
        self.assertIn("FAILED  month 2026-09", out)
        self.assertNotEqual(code, 0)

    def test_dry_run_nothing_to_post_only_when_all_months_clean(self):
        tk = DatedTK()
        run(w40(), tk, apply=True)
        tk.time = [r for r in tk.time if r["date"].startswith("2026-09")]  # Oct missing again
        out, _ = run(w40(), tk, apply=False)
        self.assertIn("2 create", out)
        self.assertNotIn(": 0 create, 0 update, 0 delete, 0 receipts", out)

    def test_unapproved_day_blocks_both_months(self):
        w = w40(); w["time_events"][3]["status"] = "Open"
        tk = DatedTK()
        out, code = run(w, tk, apply=True)
        self.assertEqual(tk.time, [])
        self.assertIn("not yet been approved", out)
        self.assertNotEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
