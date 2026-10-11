"""Every target shipped with time-assistant must be documented and pass the contract."""
import importlib
import inspect
import os
import unittest

import _paths  # noqa: F401  (puts the repo root on sys.path)
from target_contract import TargetContract
from time_assistant import config as conf
from time_assistant import targets as registry
from time_assistant.targets.base import Target


def semantic_table():
    """Header and rows of the cross-system table at the end of docs/data-convention.md."""
    path = os.path.join(_paths.ROOT, "docs", "data-convention.md")
    with open(path, encoding="utf-8") as f:
        text = f.read()
    section = text.split("## Semantic data convention across systems", 1)[1]
    lines = [ln.strip() for ln in section.splitlines() if ln.strip().startswith("|")]
    cells = [[c.strip() for c in ln.strip("|").split("|")] for ln in lines]
    return cells[0], cells[2:]          # skip the |---| separator


class RegistryTests(unittest.TestCase):
    def test_builtin_targets_are_complete(self):
        for cls in registry.BUILTIN:
            with self.subTest(target=cls.type):
                self.assertTrue(issubclass(cls, Target))
                self.assertRegex(cls.type, conf.NAME_RE)
                self.assertTrue(cls.display_name)
                self.assertIs(registry.TARGETS[cls.type], cls)
                if cls.supports_receipts:
                    self.assertTrue(cls.supports_expenses, "receipts need expenses")

    def test_builtin_targets_have_a_docs_page(self):
        for cls in registry.BUILTIN:
            path = os.path.join(_paths.ROOT, "docs", "targets", f"{cls.type}.md")
            self.assertTrue(os.path.isfile(path), f"missing {path}")

    def test_builtin_targets_have_a_column_in_the_semantic_table(self):
        header, rows = semantic_table()
        for cls in registry.BUILTIN:
            with self.subTest(target=cls.type):
                self.assertTrue(any(cell.startswith(cls.display_name) for cell in header),
                                f"docs/data-convention.md: add a '{cls.display_name} (target)' column "
                                f"to the semantic table (docs/adding-a-target.md)")

    def test_semantic_table_rows_are_complete(self):
        header, rows = semantic_table()
        for row in rows:
            with self.subTest(row=row[0]):
                self.assertEqual(len(row), len(header), "every row needs one cell per column")
                if not row[0].startswith("**"):          # bold rows are section headings
                    self.assertTrue(all(row), "fill every cell; use — if the system has no such field")

    def test_builtin_targets_run_the_contract_suite(self):
        for cls in registry.BUILTIN:
            with self.subTest(target=cls.type):
                module = importlib.import_module(f"test_target_{cls.type}")
                suites = [c for _, c in inspect.getmembers(module, inspect.isclass)
                          if issubclass(c, TargetContract) and c is not TargetContract
                          and issubclass(c, unittest.TestCase) and c.target_type == cls.type]
                self.assertTrue(suites, f"tests/test_target_{cls.type}.py needs a TargetContract "
                                        f"subclass with target_type = {cls.type!r}")

    def test_unknown_type_is_a_clear_error(self):
        with self.assertRaises(SystemExit) as e:
            registry.get("nope")
        self.assertIn("timekeeper", str(e.exception))


if __name__ == "__main__":
    unittest.main()
