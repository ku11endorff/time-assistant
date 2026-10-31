"""docs/guide.html: self-contained, its links and commands match the repository, and its
config builder (run in node) produces configs that sync.py itself accepts."""
import json
import os
import re
import shutil
import subprocess
import sys
import unittest
from unittest import mock

import _paths  # noqa: F401  (puts the repo root on sys.path)
from time_assistant import config as conf

ROOT = _paths.ROOT
GUIDE = os.path.join(ROOT, "docs", "guide.html")
sys.path.insert(0, os.path.join(ROOT, "tools"))
import make_cloud_env  # noqa: E402

with open(GUIDE, encoding="utf-8") as _f:
    HTML = _f.read()
LOGIC = re.search(r"/\* LOGIC-START \*/(.*?)/\* LOGIC-END \*/", HTML, re.S).group(1)
NODE = shutil.which("node")

VALID = {
    "targetName": "client", "username": "you@example.com", "sourceProjectIds": "1000001",
    "expenseProjectIds": "2000001, 2000002", "userId": "100", "projectId": "5001",
    "activities": [{"src": "1001", "act": "201", "tc": "301"}, {"src": "", "act": "202", "tc": "302"}],
    "expenses": True, "wagecode": "401", "categoryId": "301", "paidBy": "self",
    "allowances": True, "domestic": "501", "foreign": "502",
    "rerunHint": "ask your agent to run the time-assistant skill again",
}


def run_logic(cases):
    """Run buildConfig/configText/envLines from the page in node for each input."""
    script = LOGIC + """
const cases = JSON.parse(require('fs').readFileSync(0, 'utf8'));
console.log(JSON.stringify(cases.map(c => {
  const r = buildConfig(c);
  return { config: r.config, problems: r.problems, warnings: r.warnings,
           text: configText(r.config), env: envLines(r.config) };
})));"""
    out = subprocess.run([NODE, "-e", script], input=json.dumps(cases), capture_output=True,
                         text=True, timeout=60)
    if out.returncode:
        raise AssertionError(out.stderr)
    return json.loads(out.stdout)


class StaticTests(unittest.TestCase):
    def test_self_contained_and_offline(self):
        self.assertTrue(HTML.lstrip().lower().startswith("<!doctype html>"))
        self.assertIn('<meta charset="utf-8">', HTML)
        self.assertIn('name="viewport"', HTML)
        self.assertRegex(HTML, r"<title>[^<]{5,}</title>")
        for tag in re.findall(r"<(?:script|link|img|iframe|source|video|audio)\b[^>]*>", HTML, re.I):
            self.assertNotRegex(tag, r"(?:src|href)\s*=\s*[\"']?(?:https?:)?//", tag)
        self.assertNotRegex(HTML, r"@import|url\(\s*[\"']?https?:")
        for banned in ("fetch(", "XMLHttpRequest", "sendBeacon", "WebSocket", "EventSource", "import("):
            self.assertNotIn(banned, HTML)

    def test_every_element_the_script_uses_exists(self):
        ids = set(re.findall(r'\bid="([^"]+)"', HTML))
        used = set(re.findall(r'\$\("([^"]+)"\)', HTML))
        self.assertEqual(sorted(i for i in used if i not in ids), [])

    def test_links_point_at_real_files(self):
        for href in set(re.findall(r'<a [^>]*href="([^"#]+)', HTML)):
            self.assertFalse(href.startswith("http"), href)
            self.assertTrue(os.path.exists(os.path.normpath(os.path.join(ROOT, "docs", href))), href)

    def test_commands_and_paths_exist_in_the_repository(self):
        subs = set(re.findall(r"python3 sync\.py (?:--config \S+ )?([a-z-]+)", HTML))
        self.assertTrue({"discover", "check-config", "plan", "apply", "validate", "version"} <= subs)
        from time_assistant import cli
        helptext = subprocess.run([sys.executable, os.path.join(ROOT, "sync.py"), "--help"],
                                  capture_output=True, text=True).stdout
        for sub in subs:
            self.assertIn(sub, helptext, f"sync.py has no command '{sub}'")
        for path in re.findall(r"\b((?:tools|examples|integrations|docs)/[\w./-]+\.(?:py|json|md))", HTML):
            self.assertTrue(os.path.exists(os.path.join(ROOT, path)), path)
        self.assertTrue(os.path.isdir(os.path.join(ROOT, "integrations", "claude", "time-assistant")))
        self.assertTrue(os.path.isdir(os.path.join(ROOT, "integrations", "claude", "time-assistant-setup")))

    def test_it_never_asks_for_a_password(self):
        self.assertNotRegex(HTML, r'type="password"')
        self.assertIn("never asks for a password", HTML)

    def test_no_personal_data(self):
        for needle in ("kullendorff", "tictac", "pro tempore", "great it", "2398384", "265333", "24894"):
            self.assertNotIn(needle, HTML.lower())


@unittest.skipUnless(NODE, "node is not installed")
class BuilderTests(unittest.TestCase):
    def test_a_complete_form_gives_a_config_that_sync_py_accepts(self):
        r = run_logic([VALID])[0]
        self.assertEqual(r["problems"], [])
        self.assertEqual(r["warnings"], [])
        cfg = json.loads(r["text"])
        self.assertEqual(conf.check(cfg), [])
        t = cfg["targets"][0]
        self.assertEqual(t["source_project_ids"], [1000001, 2000001, 2000002])
        self.assertEqual(t["settings"], {"user_id": 100, "project_id": 5001})
        self.assertEqual(t["expense_map"]["default"],
                         {"wagecode_id": 401, "receipt_category_id": 301, "paid_by": "self"})
        self.assertEqual(sorted(t["allowance_map"]), ["domestic", "foreign"])
        self.assertEqual([m.get("source_activity_id") for m in t["time_map"]], [1001, None])

    def test_variants_are_all_valid(self):
        cases = [dict(VALID, expenses=False, allowances=False),
                 dict(VALID, paidBy="company", categoryId=""),
                 dict(VALID, paidBy="", categoryId="", rerunHint=""),
                 dict(VALID, allowances=True, domestic="501", foreign=""),
                 dict(VALID, targetName="partner-2", expenseProjectIds="", sourceProjectIds="1000001 1000002")]
        for case, r in zip(cases, run_logic(cases)):
            self.assertEqual(r["problems"], [], case)
            self.assertEqual(conf.check(json.loads(r["text"])), [], case)

    def test_without_a_username_it_is_a_warning_and_fine_in_a_cloud_session(self):
        r = run_logic([dict(VALID, username="")])[0]
        self.assertEqual(r["problems"], [])
        self.assertEqual(len(r["warnings"]), 1)
        cfg = json.loads(r["text"])
        self.assertTrue(any("username" in p for p in conf.check(cfg)))
        with mock.patch.dict(os.environ, {"TIME_ASSISTANT_AUTH": "proxy"}):
            self.assertEqual(conf.check(cfg), [])

    def test_mistakes_are_reported_and_nothing_is_offered(self):
        bad = [dict(VALID, targetName="My Client"), dict(VALID, sourceProjectIds="", expenseProjectIds=""),
               dict(VALID, sourceProjectIds="abc"), dict(VALID, userId=""), dict(VALID, projectId="12x"),
               dict(VALID, activities=[]), dict(VALID, activities=[{"src": "1", "act": "2", "tc": ""}]),
               dict(VALID, activities=[{"src": "1", "act": "2", "tc": "3"}, {"src": "1", "act": "4", "tc": "5"}]),
               dict(VALID, activities=[{"src": "", "act": "2", "tc": "3"}, {"src": "", "act": "4", "tc": "5"}]),
               dict(VALID, wagecode=""), dict(VALID, allowances=True, domestic="", foreign="")]
        for case, r in zip(bad, run_logic(bad)):
            self.assertTrue(r["problems"], case)

    def test_cloud_environment_lines_match_make_cloud_env(self):
        r = run_logic([VALID])[0]
        cfg = json.loads(r["text"])
        self.assertEqual(r["env"]["text"], make_cloud_env.build(cfg))
        self.assertEqual(r["env"]["problem"], "")
        q = run_logic([dict(VALID, rerunHint="it's done")])[0]
        self.assertTrue(q["env"]["problem"])


if __name__ == "__main__":
    unittest.main()
