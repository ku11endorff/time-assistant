"""Receipt category and paid-by, VAT, half-day allowances, receipt attachment detection,
cloud-session mode (proxy login, config from the environment) and the two cloud tools."""
import base64
import copy
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

import _paths  # noqa: F401  (puts the repo root on sys.path)
from fake_target import WEEK, allowance, expense, ops
from test_target_timekeeper import FakeTimeKeeperAPI, connect, sync, tk_config
from time_assistant import config as conf
from time_assistant import credentials, engine
from time_assistant.targets import timekeeper
from time_assistant.week import validate_week

sys.path.insert(0, os.path.join(_paths.ROOT, "tools"))
import make_cloud_env  # noqa: E402
import save_receipt  # noqa: E402

EXAMPLE_EXPENSES = os.path.join(_paths.ROOT, "examples", "week.example-expenses.json")
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 200


def config_with_category(**m):
    return tk_config(expense_map={"default": dict({"wagecode_id": 44, "receipt_category_id": 77,
                                                   "paid_by": "self"}, **m)})


class ReceiptCategoryTests(unittest.TestCase):
    def week(self, **kw):
        w = copy.deepcopy(WEEK)
        w["expenses"] = [expense(vat_ore=0, **kw)]
        return w

    def test_row_carries_category_paid_by_and_vat(self):
        api = FakeTimeKeeperAPI()
        sync(api, self.week(), config_with_category())
        r = api.exp[0]
        self.assertEqual((r["receiptCategoryID"], r["receiptPaymentType"], r["receiptVATAmount"]),
                         (77, 0, 0.0))

    def test_company_paid_and_vat_amount(self):
        api = FakeTimeKeeperAPI()
        w = copy.deepcopy(WEEK)
        w["expenses"] = [expense(vat_ore=1768)]
        sync(api, w, config_with_category(paid_by="company"))
        r = api.exp[0]
        self.assertEqual((r["receiptPaymentType"], r["receiptVATAmount"]), (1, 17.68))

    def test_without_the_options_rows_are_as_before(self):
        api = FakeTimeKeeperAPI()
        w = copy.deepcopy(WEEK)
        w["expenses"] = [expense()]
        sync(api, w)
        self.assertFalse({"receiptCategoryID", "receiptPaymentType", "receiptVATAmount"} & set(api.exp[0]))

    def test_a_changed_category_is_updated_not_duplicated(self):
        api = FakeTimeKeeperAPI()
        w = self.week()
        sync(api, w, config_with_category())
        plans = sync(api, w, config_with_category(receipt_category_id=78))
        self.assertEqual(ops(plans).get("update"), 1)
        self.assertEqual(len(api.exp), 1)
        self.assertEqual(api.exp[0]["receiptCategoryID"], 78)
        self.assertEqual(ops(sync(api, w, config_with_category(receipt_category_id=78))).get("update", 0), 0)

    def test_config_problems_and_note(self):
        bad = tk_config(expense_map={"default": {"wagecode_id": 44, "receipt_category_id": "x",
                                                 "paid_by": "bank"}})
        problems = timekeeper.TimeKeeperTarget.check_settings(bad)
        self.assertTrue(any("receipt_category_id" in p for p in problems))
        self.assertTrue(any("paid_by" in p for p in problems))
        self.assertEqual(timekeeper.TimeKeeperTarget.check_settings(config_with_category()), [])
        notes = conf.feature_notes({"targets": [tk_config()]})
        self.assertTrue(any("receipt_category_id" in n for n in notes))
        self.assertFalse(any("receipt_category_id" in n for n in conf.feature_notes(
            {"targets": [config_with_category()]})))


class AllowanceQuantityTests(unittest.TestCase):
    def test_half_day_keeps_the_row_total(self):
        api = FakeTimeKeeperAPI()
        w = copy.deepcopy(WEEK)
        half = allowance("6-20261005", date="2026-10-05", amount=14500)
        half["quantity"] = 0.5
        w["expenses"] = [half]
        config = tk_config(allowance_map={"domestic": {"wagecode_id": 61}})
        sync(api, w, config)
        r = api.exp[0]
        self.assertEqual((r["quantity"], r["price"]), (0.5, 290.0))
        self.assertEqual(r["quantity"] * r["price"], 145.0)

    def test_quantity_validation(self):
        w = copy.deepcopy(WEEK)
        a = allowance("6-1", amount=1000)
        for bad in (0, 1.5, "1", True):
            a["quantity"] = bad
            w["expenses"] = [dict(a)]
            self.assertTrue(any("quantity" in e for e in validate_week(w)), bad)
        a["quantity"] = 0.5
        w["expenses"] = [dict(a)]
        self.assertEqual(validate_week(w), [])
        w["expenses"] = [dict(expense(), quantity=1)]
        self.assertTrue(any("only for allowances" in e for e in validate_week(w)))

    def test_vat_validation(self):
        w = copy.deepcopy(WEEK)
        w["expenses"] = [expense(vat_ore=-1)]
        self.assertTrue(any("vat_ore" in e for e in validate_week(w)))
        w["expenses"] = [expense(vat_ore=1.5)]
        self.assertTrue(any("vat_ore" in e for e in validate_week(w)))

    def test_example_with_expenses_is_valid(self):
        with open(EXAMPLE_EXPENSES, encoding="utf-8") as f:
            self.assertEqual(validate_week(json.load(f)), [])


class AttachedFilesTests(unittest.TestCase):
    def test_original_file_name_is_recognised(self):
        api = mock.Mock()
        api.expense_files.return_value = [{"id": 1, "originalFileName": "r.jpg"}]
        t = connect(tk_config(), api)
        self.assertEqual(t.attached_files(mock.Mock(id=5)), ["r.jpg"])
        api.expense_files.return_value = [{"fileName": "old.jpg"}]
        self.assertEqual(t.attached_files(mock.Mock(id=5)), ["old.jpg"])


class CloudModeTests(unittest.TestCase):
    def test_proxy_mode_sends_no_authorization_and_needs_no_secret(self):
        with mock.patch.dict(os.environ, {"TIME_ASSISTANT_AUTH": "proxy"}):
            self.assertTrue(credentials.proxy_mode())
            self.assertEqual(credentials.get_secrets("client", ("password",)), {})
            api = timekeeper.TimeKeeperAPI("", "", proxy_auth=True)
        self.assertNotIn("Authorization", api.headers)
        self.assertIn("Authorization", timekeeper.TimeKeeperAPI("u", "p").headers)

    def test_username_is_not_required_in_proxy_mode(self):
        t = tk_config()
        del t["username"]
        cfg = {"version": 2, "targets": [t]}
        self.assertTrue(any("username" in p for p in conf.check(cfg)))
        with mock.patch.dict(os.environ, {"TIME_ASSISTANT_AUTH": "proxy"}):
            self.assertFalse(any("username" in p for p in conf.check(cfg)))

    def test_config_comes_from_the_environment_when_the_file_is_missing(self):
        cfg = {"version": 2, "targets": [tk_config()]}
        missing = os.path.join(tempfile.mkdtemp(), "config.json")
        with mock.patch.dict(os.environ, {conf.ENV_CONFIG: json.dumps(cfg)}):
            self.assertEqual(conf.read(missing)["targets"][0]["name"], "client")
        with mock.patch.dict(os.environ, {}, clear=True), self.assertRaises(SystemExit):
            conf.read(missing)
        with mock.patch.dict(os.environ, {conf.ENV_CONFIG: "{not json"}), self.assertRaises(SystemExit) as cm:
            conf.read(missing)
        self.assertIn(conf.ENV_CONFIG, str(cm.exception))

    def test_a_config_file_wins_over_the_environment(self):
        d = tempfile.mkdtemp()
        path = os.path.join(d, "config.json")
        with open(path, "w") as f:
            json.dump({"version": 2, "targets": [tk_config(name="from-file")]}, f)
        with mock.patch.dict(os.environ, {conf.ENV_CONFIG: json.dumps(
                {"version": 2, "targets": [tk_config(name="from-env")]})}):
            self.assertEqual(conf.read(path)["targets"][0]["name"], "from-file")

    def test_make_cloud_env_drops_notes_and_has_no_secrets(self):
        cfg = {"version": 2, "_comment": "x", "targets": [dict(tk_config(), _note="y")]}
        text = make_cloud_env.build(cfg)
        lines = text.splitlines()
        self.assertEqual(lines[0], "TIME_ASSISTANT_AUTH=proxy")
        self.assertTrue(lines[1].startswith("TIME_ASSISTANT_CONFIG_JSON='{"))
        payload = json.loads(lines[1].split("=", 1)[1].strip("'"))
        self.assertNotIn("_comment", payload)
        self.assertNotIn("_note", payload["targets"][0])
        self.assertNotIn("password", text.lower())
        with self.assertRaises(ValueError):
            make_cloud_env.build({"targets": [{"name": "it's"}]})


class SaveReceiptTests(unittest.TestCase):
    def b64(self, raw=JPEG):
        return base64.b64encode(raw).decode()

    def test_decodes_plain_data_uri_and_json(self):
        for text in (self.b64(), "data:image/jpeg;base64," + self.b64(),
                     json.dumps({"content": [{"data": self.b64()}]})):
            raw, kind = save_receipt.decode(text)
            self.assertEqual((raw, kind), (JPEG, "jpg"))

    def test_rejects_garbage_and_truncated_data(self):
        with self.assertRaises(ValueError):
            save_receipt.decode("short")
        with self.assertRaises(ValueError):
            save_receipt.decode(self.b64(b"not an image" * 20))
        with self.assertRaises(ValueError):
            save_receipt.decode("!!!" + self.b64())

    def test_file_is_named_by_what_it_is(self):
        d = tempfile.mkdtemp()
        src = os.path.join(d, "result.txt")
        with open(src, "w") as f:
            f.write(self.b64(b"%PDF-1.4" + b"\x00" * 200))
        out = os.path.join(d, "receipts", "5-1.jpg")
        self.assertEqual(save_receipt.main(["x", src, out]), 0)
        self.assertTrue(os.path.isfile(os.path.join(d, "receipts", "5-1.pdf")))
        self.assertFalse(os.path.exists(out))
        with open(src, "w") as f:
            f.write("nonsense")
        self.assertEqual(save_receipt.main(["x", src, os.path.join(d, "bad.jpg")]), 1)


if __name__ == "__main__":
    unittest.main()
