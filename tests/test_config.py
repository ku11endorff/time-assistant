import copy
import json
import os
import unittest

import _paths  # noqa: F401  (puts the repo root on sys.path)
from fake_target import cfg, target_cfg  # also registers the memory targets
from time_assistant import config as conf


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


class CheckTests(unittest.TestCase):
    def test_example_configs_are_valid(self):
        for path in (_paths.EXAMPLE_CONFIG, _paths.TWO_TARGETS_CONFIG):
            with self.subTest(path=os.path.basename(path)):
                self.assertEqual(conf.check(load(path)), [])

    def test_typical_mistakes_are_reported(self):
        bad = cfg(target_cfg(name="Client 1", source_projects=["1000001"], delete_stale="no",
                             time_map=[{"source_activity_id": 1001}, {"source_activity_id": 1001, "code": "T"}],
                             settings={}),
                  target_cfg(name="other", type_="nope"))
        bad["version"] = 1
        problems = " | ".join(conf.check(bad))
        for needle in ("'version' must be 2", "'name' must be lowercase", "source_project_ids",
                       "'delete_stale' must be true or false", "'code' is required",
                       "mapped twice", "settings.project is required", "unknown 'type' 'nope'"):
            self.assertIn(needle, problems)

    def test_names_must_be_unique_and_targets_present(self):
        self.assertTrue(any("used twice" in p for p in conf.check(cfg(target_cfg(), target_cfg(project="P2")))))
        self.assertTrue(conf.check({"version": 2, "targets": []}))

    def test_same_place_twice_is_refused(self):
        two = cfg(target_cfg(), target_cfg(name="again"))
        self.assertTrue(any("overwrite each other's rows" in p for p in conf.check(two)))

    def test_old_format_is_detected(self):
        self.assertTrue(conf.is_legacy(load(os.path.join(_paths.FIXTURES, "config.v1.json"))))
        self.assertFalse(conf.is_legacy(load(_paths.EXAMPLE_CONFIG)))

    def test_accessors_and_defaults(self):
        c = cfg()
        self.assertEqual(conf.rerun_hint(c), "run the export again")
        self.assertEqual(conf.accepted_statuses(c), ("Approved", "Certified"))
        self.assertEqual(conf.source_name({}), "the source system")
        c["source"]["rerun_hint"] = "run /my-skill again."
        self.assertEqual(conf.rerun_hint(c), "run /my-skill again")


class MigrateTests(unittest.TestCase):
    def setUp(self):
        self.old = load(os.path.join(_paths.FIXTURES, "config.v1.json"))

    def test_old_example_converts_to_a_valid_config(self):
        new = conf.migrate(self.old, "you@example.com")
        self.assertEqual(conf.check(new), [])
        t = new["targets"][0]
        self.assertEqual((t["type"], t["username"], t["source_project_ids"]),
                         ("timekeeper", "you@example.com", [1000001]))
        self.assertEqual((t["settings"]["user_id"], t["settings"]["project_id"]), (100, 5001))
        self.assertEqual(t["time_map"][0]["source_activity_id"], 1001)
        self.assertEqual((t["time_map"][0]["activity_id"], t["time_map"][0]["timecode_id"]), (201, 301))
        self.assertEqual(t["expense_map"]["default"]["wagecode_id"], 401)
        self.assertEqual(new["source"]["rerun_hint"], "run the export again")
        self.assertNotIn("rerun_hint", new["approval"])

    def test_missing_username_is_reported_after_conversion(self):
        new = conf.migrate(copy.deepcopy(self.old))
        self.assertTrue(any("'username' is required" in p for p in conf.check(new)))


if __name__ == "__main__":
    unittest.main()
