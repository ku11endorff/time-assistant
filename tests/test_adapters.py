import importlib.util
import os
import unittest

import _paths  # noqa: F401  (puts the repo root on sys.path)

spec = importlib.util.spec_from_file_location(
    "build_adapters", os.path.join(_paths.ROOT, "tools", "build_adapters.py"))
ba = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ba)


class AdapterTests(unittest.TestCase):
    def test_generated_instruction_files_are_current(self):
        for rel, text in ba.render().items():
            with open(os.path.join(_paths.ROOT, rel), encoding="utf-8") as f:
                self.assertEqual(f.read(), text, f"{rel} is stale: run python3 tools/build_adapters.py")

    def test_skill_has_frontmatter_first(self):
        text = ba.render()["integrations/claude/time-assistant/SKILL.md"]
        self.assertTrue(text.startswith("---\nname: time-assistant\n"))


if __name__ == "__main__":
    unittest.main()
