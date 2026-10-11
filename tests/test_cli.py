"""The sync.py commands, end to end with in-memory targets."""
import contextlib
import io
import json
import os
import shutil
import tempfile
import unittest

import _paths  # noqa: F401  (puts the repo root on sys.path)
from fake_target import WEEK, MemoryBackend, MemoryTarget, cfg, target_cfg
from time_assistant import cli
from time_assistant import config as conf


class CliTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.backend = MemoryBackend()

    def tearDown(self):
        self.dir.cleanup()

    def write(self, name, data):
        path = os.path.join(self.dir.name, name)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f)
        return path

    def main(self, *argv):
        out, code = io.StringIO(), 0
        connect = lambda tcfg: MemoryTarget(tcfg, backend=self.backend)  # noqa: E731
        with contextlib.redirect_stdout(out):
            try:
                cli.main(list(argv), connect=connect)
            except SystemExit as e:
                code = e.code if isinstance(e.code, int) else 1
                print(e.code)
        return out.getvalue(), code

    def test_validate(self):
        out, code = self.main("validate", "--week", _paths.EXAMPLE_WEEK)
        self.assertEqual(code, 0)
        self.assertIn("valid (5 time events, 0 expenses)", out)
        out, code = self.main("validate", "--week", self.write("bad.json", {"from": "x"}))
        self.assertNotEqual(code, 0)

    def test_invalid_week_blocks_plan(self):
        c = self.write("c.json", cfg())
        out, code = self.main("--config", c, "plan", "--week", self.write("bad.json", {"from": "x"}))
        self.assertNotEqual(code, 0)
        self.assertIn("is not a valid week file", out)

    def test_plan_then_apply_then_clean_plan(self):
        c, w = self.write("c.json", cfg()), self.write("w.json", WEEK)
        out, code = self.main("--config", c, "plan", "--week", w)
        self.assertEqual(code, 0, out)
        self.assertEqual(self.backend.rows["time"], [])
        out, code = self.main("--config", c, "apply", "--week", w)
        self.assertEqual(code, 0, out)
        self.assertEqual(len(self.backend.rows["time"]), 5)
        out, _ = self.main("--config", c, "plan", "--week", w)
        self.assertIn("\ndry run - nothing written: 0 create, 0 update, 0 delete, 0 receipts", out)

    def test_target_option(self):
        two = cfg(target_cfg(), target_cfg(name="partner", project="P9"))
        c, w = self.write("c.json", two), self.write("w.json", WEEK)
        out, code = self.main("--config", c, "plan", "--week", w, "--target", "partner")
        self.assertIn("=== partner (Memory) ===", out)
        self.assertNotIn("=== client", out)

    def test_check_config(self):
        out, code = self.main("--config", self.write("c.json", cfg()), "check-config")
        self.assertEqual(code, 0, out)
        self.assertIn("valid (1 target(s))", out)
        bad = cfg()
        del bad["targets"][0]["time_map"]
        out, code = self.main("--config", self.write("bad.json", bad), "check-config")
        self.assertNotEqual(code, 0)
        self.assertIn("'time_map' needs at least one entry", out)

    def test_old_config_points_to_migrate(self):
        old = os.path.join(_paths.FIXTURES, "config.v1.json")
        out, code = self.main("--config", old, "plan", "--week", _paths.EXAMPLE_WEEK)
        self.assertNotEqual(code, 0)
        self.assertIn("migrate-config", out)

    def test_migrate_config_keeps_a_backup_and_uses_tk_user(self):
        path = os.path.join(self.dir.name, "config.json")
        shutil.copyfile(os.path.join(_paths.FIXTURES, "config.v1.json"), path)
        with open(os.path.join(self.dir.name, ".tk_user"), "w") as f:
            f.write("you@example.com\n")
        out, code = self.main("--config", path, "migrate-config")
        self.assertEqual(code, 0, out)
        self.assertTrue(os.path.exists(path + ".bak-v1"))
        with open(path, encoding="utf-8") as f:
            new = json.load(f)
        self.assertEqual(conf.check(new), [])
        self.assertEqual(new["targets"][0]["username"], "you@example.com")
        self.assertIn("security add-generic-password -s time-assistant:timekeeper -a password", out)
        out, _ = self.main("--config", path, "migrate-config")
        self.assertIn("already in the current format", out)

    def test_targets_lists_timekeeper(self):
        out, code = self.main("targets")
        self.assertIn("timekeeper", out)
        self.assertIn("docs/targets/timekeeper.md", out)

    def test_discover_runs_on_an_incomplete_config(self):
        partial = cfg(target_cfg(settings={}))
        out, code = self.main("--config", self.write("c.json", partial), "discover")
        self.assertEqual(code, 0, out)
        self.assertIn("=== client (Memory) ===", out)


if __name__ == "__main__":
    unittest.main()
