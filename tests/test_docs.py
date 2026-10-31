"""The documentation hangs together: every relative link and heading anchor resolves, and
the hand-written setup skill has the front matter agents need."""
import glob
import os
import re
import unittest

import _paths  # noqa: F401  (puts the repo root on sys.path)

ROOT = _paths.ROOT
LINK = re.compile(r"(?<!!)\[[^\]]*\]\(([^)\s]+)\)")
HEADING = re.compile(r"^#{1,6}\s+(.*?)\s*#*\s*$", re.M)


def slug(heading: str) -> str:
    h = re.sub(r"[`*]", "", heading).strip().lower()
    h = re.sub(r"[^\w\- ]", "", h)
    return h.replace(" ", "-")


def anchors(path: str) -> set:
    with open(path, encoding="utf-8") as f:
        text = re.sub(r"```.*?```", "", f.read(), flags=re.S)
    return {slug(m.group(1)) for m in HEADING.finditer(text)}


def markdown_files():
    files = [os.path.join(ROOT, n) for n in ("README.md", "CHANGELOG.md", "CONTRIBUTING.md")]
    files += glob.glob(os.path.join(ROOT, "docs", "**", "*.md"), recursive=True)
    return [f for f in files if os.path.isfile(f)]


class LinkTests(unittest.TestCase):
    def test_relative_links_and_anchors_resolve(self):
        problems = []
        for md in markdown_files():
            with open(md, encoding="utf-8") as f:
                text = re.sub(r"```.*?```", "", f.read(), flags=re.S)
            for target in LINK.findall(text):
                if re.match(r"^(https?:|mailto:)", target):
                    continue
                path, _, frag = target.partition("#")
                dest = os.path.normpath(os.path.join(os.path.dirname(md), path)) if path else md
                rel = os.path.relpath(md, ROOT)
                if not os.path.exists(dest):
                    problems.append(f"{rel}: {target} does not exist")
                elif frag and dest.endswith(".md") and frag not in anchors(dest):
                    problems.append(f"{rel}: {target}: no heading '{frag}'")
        self.assertEqual(problems, [])

    def test_the_new_guides_exist_and_are_linked_from_the_readme(self):
        with open(os.path.join(ROOT, "README.md"), encoding="utf-8") as f:
            readme = f.read()
        for name in ("how-it-works", "getting-started", "claude-project-setup", "cloud-sessions"):
            self.assertTrue(os.path.isfile(os.path.join(ROOT, "docs", f"{name}.md")), name)
            self.assertIn(f"docs/{name}.md", readme)
        self.assertTrue(os.path.isfile(os.path.join(ROOT, "docs", "guide.html")))
        self.assertIn("docs/guide.html", readme)


class SetupSkillTests(unittest.TestCase):
    path = os.path.join(ROOT, "integrations", "claude", "time-assistant-setup", "SKILL.md")

    def test_front_matter(self):
        with open(self.path, encoding="utf-8") as f:
            text = f.read()
        m = re.match(r"^---\nname: (\S+)\ndescription: (.+)\n---\n", text)
        self.assertIsNotNone(m, "SKILL.md must start with name and description front matter")
        self.assertEqual(m.group(1), "time-assistant-setup")
        self.assertGreater(len(m.group(2)), 40)

    def test_the_guide_never_asks_for_secrets_and_points_to_real_docs(self):
        with open(self.path, encoding="utf-8") as f:
            text = f.read()
        self.assertIn("Never ask for, accept or handle a password", text)
        for doc in re.findall(r"`(docs/[\w\-/]+\.md)`", text):
            self.assertTrue(os.path.isfile(os.path.join(ROOT, doc)), doc)


if __name__ == "__main__":
    unittest.main()
