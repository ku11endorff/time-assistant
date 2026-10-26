"""Versions, the agent playbook version, feature notes and release notes."""
import contextlib
import copy
import importlib.util
import io
import json
import os
import tempfile
import unittest

import _paths  # noqa: F401  (puts the repo root on sys.path)
from fake_target import WEEK, MemoryTarget, cfg, target_cfg
from time_assistant import __version__, cli
from time_assistant import config as conf
from time_assistant import week as weekfile

PV = weekfile.PLAYBOOK_VERSION


def load_tool(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(_paths.ROOT, "tools", f"{name}.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def read(*parts):
    with open(os.path.join(_paths.ROOT, *parts), encoding="utf-8") as f:
        return f.read()


def write_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)


def run_cli(*argv):
    out, code = io.StringIO(), 0
    with contextlib.redirect_stdout(out):
        try:
            cli.main(list(argv), connect=lambda t: MemoryTarget(t))
        except SystemExit as e:
            code = e.code if isinstance(e.code, int) else 1
    return out.getvalue(), code


class PlaybookVersionTests(unittest.TestCase):
    def test_playbook_and_example_carry_the_current_version(self):
        playbook = read("docs", "agent-playbook.md")
        self.assertIn(f"Playbook version: {PV}\n", playbook)
        self.assertIn(f'"playbook_version": {PV}', playbook)
        self.assertEqual(WEEK["playbook_version"], PV)

    def test_generated_skill_carries_it_too(self):
        skill = load_tool("build_adapters").render()["integrations/claude/time-assistant/SKILL.md"]
        self.assertIn(f"Playbook version: {PV}\n", skill)

    def test_notice(self):
        w = copy.deepcopy(WEEK)
        self.assertIsNone(weekfile.playbook_notice(w))
        del w["playbook_version"]
        self.assertIn("no playbook_version", weekfile.playbook_notice(w))
        w["playbook_version"] = PV - 1
        self.assertIn(f"made with agent playbook {PV - 1}", weekfile.playbook_notice(w))
        w["playbook_version"] = PV + 1
        self.assertIn("Update time-assistant", weekfile.playbook_notice(w))

    def test_must_be_a_whole_number(self):
        w = dict(copy.deepcopy(WEEK), playbook_version="4")
        self.assertTrue(any("playbook_version" in e for e in weekfile.validate_week(w)))

    def test_validate_and_plan_warn_about_old_instructions(self):
        old = copy.deepcopy(WEEK)
        del old["playbook_version"]
        with tempfile.TemporaryDirectory() as d:
            wp, cp = os.path.join(d, "w.json"), os.path.join(d, "c.json")
            write_json(wp, old)
            write_json(cp, cfg())
            out, code = run_cli("validate", "--week", wp)
            self.assertEqual(code, 0)
            self.assertIn("WARN    this week file has no playbook_version", out)
            out, code = run_cli("--config", cp, "plan", "--week", wp)
            self.assertEqual(code, 0, out)
            self.assertIn("WARN    this week file has no playbook_version", out)


class VersionCommandTests(unittest.TestCase):
    def test_version_command(self):
        out, code = run_cli("version")
        self.assertEqual(code, 0)
        self.assertIn(f"time-assistant {__version__}", out)
        self.assertIn(f"agent playbook {PV}", out)


class FeatureNoteTests(unittest.TestCase):
    def test_unused_optional_features_are_noted(self):
        notes = " | ".join(conf.feature_notes(cfg(target_cfg(expense_map={}))))
        self.assertIn("target 'client': no expense_map", notes)
        self.assertIn("can take daily allowances", notes)

    def test_partly_mapped_allowances(self):
        notes = conf.feature_notes(cfg(target_cfg(allowance_map={"domestic": {"code": "D"}})))
        self.assertEqual(notes, ["target 'client': no allowance_map entry for foreign allowances; "
                                 "those are listed but not written"])

    def test_no_notes_when_everything_is_used_or_unsupported(self):
        full = target_cfg(allowance_map={"domestic": {"code": "D"}, "foreign": {"code": "F"}})
        basic = target_cfg(name="basic", project="P2", type_="memory-basic")
        self.assertEqual(conf.feature_notes(cfg(full, basic)), [])

    def test_check_config_prints_notes(self):
        with tempfile.TemporaryDirectory() as d:
            cp = os.path.join(d, "c.json")
            write_json(cp, cfg())
            out, code = run_cli("--config", cp, "check-config")
        self.assertEqual(code, 0)
        self.assertIn("NOTE    target 'client': can take daily allowances", out)


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.tool = load_tool("release_notes")
        self.changelog = read("CHANGELOG.md")

    def test_current_version_is_releasable(self):
        self.assertEqual(self.tool.problems(__version__, self.changelog), [])
        heading, body = self.tool.section(self.changelog, __version__)
        self.assertIn(f"Agent playbook: {PV}", body)
        self.assertIn("### Upgrading", body)

    def test_mismatches_are_refused(self):
        self.assertTrue(self.tool.problems("9.9.9", self.changelog))
        unreleased = self.changelog.replace(f"## [{__version__}] - ", f"## [{__version__}] - Unreleased ", 1)
        self.assertTrue(any("Unreleased" in p for p in self.tool.problems(__version__, unreleased)))
        no_section = self.changelog.replace(f"## [{__version__}]", "## [x]", 1)
        self.assertTrue(any("no '## [" in p for p in self.tool.problems(__version__, no_section)))

    def test_section_stops_at_the_next_version(self):
        body = self.tool.section(self.changelog, "0.3.0")[1]
        self.assertIn("Daily allowances", body)
        self.assertNotIn("Several targets instead of one", body)


class CheckVersionTests(unittest.TestCase):
    def setUp(self):
        self.tool = load_tool("check_version")
        self.template = read(".github", "pull_request_template.md")

    def tick(self, *bumps):
        body = self.template
        for b in bumps:
            body = body.replace(f"- [ ] {b} (", f"- [x] {b} (", 1)
        return body

    def test_template_asks_and_parses(self):
        self.assertIn("tick one of Major / Minor / Patch", self.tool.bump_from_body(self.template)[1])
        for b in ("Major", "Minor", "Patch"):
            self.assertEqual(self.tool.bump_from_body(self.tick(b)), (b.lower(), None))
        self.assertIn("only one", self.tool.bump_from_body(self.tick("Minor", "Patch"))[1])
        self.assertEqual(self.tool.bump_from_body("- [X] **Major**")[0], "major")
        self.assertIn("tick one", self.tool.bump_from_body(None)[1])

    def test_next_version(self):
        self.assertEqual([self.tool.next_version("0.4.1", b) for b in ("major", "minor", "patch")],
                         ["1.0.0", "0.5.0", "0.4.2"])
        with self.assertRaises(ValueError):
            self.tool.next_version("", "patch")

    def test_version_must_match_the_ticked_bump(self):
        # Derived from the current version, so the test survives every release.
        a, b, c = (int(x) for x in __version__.split("."))
        if c:
            base, bump, other = f"{a}.{b}.{c - 1}", "Patch", "Minor"
        elif b:
            base, bump, other = f"{a}.{b - 1}.0", "Minor", "Patch"
        else:
            base, bump, other = f"{a - 1}.0.0", "Major", "Patch"
        changelog = read("CHANGELOG.md")
        self.assertEqual(self.tool.problems(self.tick(bump), base, __version__, changelog), [])
        wrong = self.tool.problems(self.tick(other), base, __version__, changelog)
        self.assertIn(f"{other.lower()} change after {base} is version", wrong[0])
        nxt = self.tool.next_version(__version__, "patch")
        missing = self.tool.problems(self.tick("Patch"), __version__, nxt, changelog)
        self.assertTrue(any(f"no '## [{nxt}]" in p for p in missing))

if __name__ == "__main__":
    unittest.main()
