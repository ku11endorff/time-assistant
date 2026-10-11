"""TimeKeeper target: the shared contract against a fake TimeKeeper API, plus the
TimeKeeper-specific details (payload shape, hours/minutes, old tags, 404s)."""
import copy
import io
import unittest
import urllib.error
from unittest import mock

import _paths  # noqa: F401  (puts the repo root on sys.path)
from fake_target import WEEK, expense, ops
from target_contract import TargetContract
from time_assistant import config as conf
from time_assistant import engine
from time_assistant.targets.timekeeper import TimeKeeperAPI, TimeKeeperTarget, extract_items


class FakeTimeKeeperAPI:
    """In-memory stand-in for TimeKeeperAPI: same methods, rows shaped like TimeKeeper's."""
    def __init__(self):
        self.time, self.exp, self.files, self.next_id = [], [], {}, 1000

    def _range(self, rows, d_from, d_to):
        return [dict(r) for r in rows if d_from <= r["date"][:10] <= d_to]

    def time_regs(self, uid, d_from, d_to):    return self._range(self.time, d_from, d_to)
    def expense_regs(self, uid, d_from, d_to): return self._range(self.exp, d_from, d_to)

    def _add(self, store, body):
        self.next_id += 1
        store.append(dict(body, id=self.next_id))

    def create_time(self, b): self._add(self.time, b)
    def create_exp(self, b):  self._add(self.exp, b)

    def update_time(self, b): self.time[:] = [dict(b) if r["id"] == b["id"] else r for r in self.time]
    def update_exp(self, b):  self.exp[:] = [dict(b) if r["id"] == b["id"] else r for r in self.exp]

    def delete_time(self, i): self.time[:] = [r for r in self.time if r["id"] != i]
    def delete_exp(self, i):  self.exp[:] = [r for r in self.exp if r["id"] != i]

    def expense_files(self, eid):
        return [{"fileName": n} for n in self.files.get(eid, [])]

    def upload_expense_file(self, eid, path):
        self.files.setdefault(eid, []).append(path.rsplit("/", 1)[-1])


def tk_config(**extra):
    t = {"name": "client", "type": "timekeeper", "username": "you@example.com",
         "source_project_ids": [1000001],
         "settings": {"user_id": 7, "project_id": 5001},
         "time_map": [{"source_activity_id": 1001, "activity_id": 22, "timecode_id": 33}],
         "expense_map": {"default": {"wagecode_id": 44}}}
    t.update(extra)
    return t


def connect(config, api):
    t = TimeKeeperTarget(config, {"password": "not-used"}, api=api)
    t.write_pause = 0
    return t


class TimeKeeperContract(TargetContract, unittest.TestCase):
    target_type = "timekeeper"

    def new_backend(self):
        return FakeTimeKeeperAPI()

    def make_target(self, config, backend):
        return connect(config, backend)

    def target_config(self):
        return tk_config()

    def add_manual_row(self, backend, config, kind, date):
        row = {"id": 1, "date": f"{date}T00:00:00", "projectID": config["settings"]["project_id"],
               "comment": "typed by hand"}
        if kind == "time":
            backend.time.append(dict(row, hours=7, minutes=30, activityID=22, timeCodeID=33))
        else:
            backend.exp.append(dict(row, wagecodeID=44, price=10, quantity=1))

    def other_scope_config(self):
        return tk_config(name="other", settings={"user_id": 7, "project_id": 6001})


def sync(api, week, config=None):
    config = config or tk_config()
    target = connect(config, api)
    plans = engine.plan_target({"version": 2, "targets": [config]}, config, target, week)
    if not any(p.errors for p in plans):
        for p in plans:
            engine.execute(p, target)
    return plans


class PayloadTests(unittest.TestCase):
    def test_time_rows_have_timekeeper_shape(self):
        api = FakeTimeKeeperAPI()
        sync(api, WEEK)
        by_date = {r["date"]: r for r in api.time}
        self.assertEqual((by_date["2026-10-05"]["hours"], by_date["2026-10-05"]["minutes"]), (7, 30))
        self.assertEqual((by_date["2026-10-06"]["hours"], by_date["2026-10-06"]["minutes"]), (8, 30))
        r = by_date["2026-10-06"]
        self.assertEqual((r["userID"], r["projectID"], r["activityID"], r["timeCodeID"], r["isInvoiced"]),
                         (7, 5001, 22, 33, False))
        self.assertEqual(r["comment"], "[ta:t:7000002]")
        self.assertEqual(by_date["2026-10-05"]["comment"],
                         "Example: weekly planning and incident follow-up [ta:t:7000001]")
        self.assertEqual(sum(r["hours"] * 60 + r["minutes"] for r in api.time), 39 * 60)

    def test_expense_rows_have_timekeeper_shape(self):
        api = FakeTimeKeeperAPI()
        w = copy.deepcopy(WEEK)
        w["expenses"] = [expense(description="Taxi")]
        sync(api, w)
        r = api.exp[0]
        self.assertEqual((r["price"], r["quantity"], r["wagecodeID"], r["projectID"], r["comment"]),
                         (312.5, 1, 44, 5001, "Taxi [ta:e:5-1]"))

    def test_rows_in_other_projects_are_not_this_targets(self):
        api = FakeTimeKeeperAPI()
        api.time.append({"id": 1, "date": "2026-10-05", "hours": 1, "minutes": 0, "projectID": 999,
                         "activityID": 22, "timeCodeID": 33, "comment": "[ta:t:7000001]"})
        plans = sync(api, WEEK, tk_config(delete_stale=True))
        self.assertEqual(ops(plans), {"create": 5})
        self.assertEqual(len(api.time), 6)              # the other project's row is untouched


class LegacyTagTests(unittest.TestCase):
    def rows_with_old_tags(self, api):
        sync(api, WEEK)
        for r in api.time:
            r["comment"] = r["comment"].replace("[ta:", "[kleer:")

    def test_rows_written_by_older_versions_still_match_without_churn(self):
        api = FakeTimeKeeperAPI()
        self.rows_with_old_tags(api)
        self.assertEqual(ops(sync(api, WEEK)), {"skip": 5})
        self.assertTrue(all("[kleer:t:" in r["comment"] for r in api.time))

    def test_changed_row_gets_the_new_tag(self):
        api = FakeTimeKeeperAPI()
        self.rows_with_old_tags(api)
        w = copy.deepcopy(WEEK)
        w["time_events"][1]["hours"] = 6.0
        self.assertEqual(ops(sync(api, w)), {"update": 1, "skip": 4})
        self.assertEqual(len(api.time), 5)
        row = next(r for r in api.time if r["date"] == "2026-10-06")
        self.assertEqual(row["comment"], "[ta:t:7000002]")


class ConfigTests(unittest.TestCase):
    def test_ids_must_be_numbers_and_base_url_https(self):
        bad = tk_config(settings={"user_id": "100", "project_id": 5001, "base_url": "http://x"})
        problems = " | ".join(conf.check({"version": 2, "targets": [bad]}))
        self.assertIn("settings.user_id must be a number", problems)
        self.assertIn("base_url must start with https://", problems)

    def test_username_and_mapping_fields_are_required(self):
        bad = tk_config(username="", time_map=[{"source_activity_id": 1001, "activity_id": 22}],
                        expense_map={"default": {}})
        problems = " | ".join(conf.check({"version": 2, "targets": [bad]}))
        for needle in ("'username' is required", "'timecode_id' is required", "'wagecode_id' is required"):
            self.assertIn(needle, problems)

    def test_two_targets_writing_to_the_same_project_are_refused(self):
        two = {"version": 2, "targets": [tk_config(), tk_config(name="again")]}
        self.assertTrue(any("overwrite each other's rows" in p for p in conf.check(two)))
        two["targets"][1]["settings"] = {"user_id": 7, "project_id": 6001}
        self.assertEqual(conf.check(two), [])


def http_error(code):
    return urllib.error.HTTPError("http://x", code, "err", {}, io.BytesIO(b'{"title":"Not Found"}'))


class HttpTests(unittest.TestCase):
    def setUp(self):
        self.api = TimeKeeperAPI("u", "p", "https://example.invalid")

    def test_404_on_registration_list_means_empty(self):
        with mock.patch("urllib.request.urlopen", side_effect=http_error(404)):
            self.assertEqual(self.api.time_regs(1, "2026-10-12", "2026-10-12"), [])
            self.assertEqual(self.api.expense_regs(1, "2026-10-12", "2026-10-12"), [])

    def test_404_on_a_write_still_fails_loudly(self):
        with mock.patch("urllib.request.urlopen", side_effect=http_error(404)):
            with self.assertRaises(SystemExit):
                self.api.create_time({"userID": 1})

    def test_other_errors_on_lists_still_fail(self):
        with mock.patch("urllib.request.urlopen", side_effect=http_error(401)):
            with self.assertRaises(SystemExit):
                self.api.time_regs(1, "2026-10-12", "2026-10-12")

    def test_response_envelope_variants(self):
        self.assertEqual(extract_items([{"a": 1}]), [{"a": 1}])
        self.assertEqual(extract_items({"Data": [{"a": 1}]}), [{"a": 1}])
        self.assertEqual(extract_items({"data": {"items": [{"a": 1}]}}), [{"a": 1}])
        self.assertEqual(extract_items(None), [])


if __name__ == "__main__":
    unittest.main()
