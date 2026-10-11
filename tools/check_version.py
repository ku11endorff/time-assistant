#!/usr/bin/env python3
"""Check that a pull request bumps the version the way its description says.

Every pull request ticks exactly one of Major / Minor / Patch in its description
(.github/pull_request_template.md) and sets time_assistant.__version__ to the next
version after the base branch's: major 0.4.1 -> 1.0.0, minor -> 0.5.0, patch -> 0.4.2.
CHANGELOG.md must have a dated section for that version. The version workflow
(.github/workflows/version.yml) runs this on every pull request:

    PR_BODY="..." python3 tools/check_version.py --base-version 0.4.1

Rules for choosing the bump: CONTRIBUTING.md#versioning.
"""
import argparse
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))

from release_notes import problems as release_problems  # noqa: E402
from time_assistant import __version__  # noqa: E402

BUMPS = ("major", "minor", "patch")
_BOX = re.compile(r"^\s*[-*]\s*\[([ xX])\]\s*\**\s*(Major|Minor|Patch)\b", re.M | re.I)
_VERSION = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


def bump_from_body(body: str):
    """(bump, None) for exactly one ticked box, else (None, problem)."""
    ticked = [m.group(2).lower() for m in _BOX.finditer(body or "") if m.group(1).lower() == "x"]
    if len(ticked) == 1:
        return ticked[0], None
    if not ticked:
        return None, ("tick one of Major / Minor / Patch under 'Version' in the pull request "
                      "description (CONTRIBUTING.md#versioning)")
    return None, f"tick only one of Major / Minor / Patch (ticked: {', '.join(ticked)})"


def next_version(base: str, bump: str) -> str:
    m = _VERSION.match(base)
    if not m:
        raise ValueError(f"not a MAJOR.MINOR.PATCH version: {base!r}")
    major, minor, patch = map(int, m.groups())
    if bump == "major":
        return f"{major + 1}.0.0"
    if bump == "minor":
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


def problems(body: str, base_version: str, version: str, changelog: str) -> list:
    bump, why = bump_from_body(body)
    if why:
        return [why]
    expected = next_version(base_version, bump)
    if version != expected:
        return [f"a {bump} change after {base_version} is version {expected}; set __version__ in "
                f"time_assistant/__init__.py to {expected} (it is {version})"]
    return release_problems(version, changelog)


def main(argv) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--base-version", required=True, help="__version__ on the base branch")
    args = ap.parse_args(argv)
    with open(os.path.join(ROOT, "CHANGELOG.md"), encoding="utf-8") as f:
        changelog = f.read()
    try:
        errs = problems(os.environ.get("PR_BODY", ""), args.base_version, __version__, changelog)
    except ValueError as e:
        errs = [f"cannot read the base branch's version: {e}"]
    for e in errs:
        print(f"ERROR   {e}")
    if not errs:
        print(f"version {__version__}: {bump_from_body(os.environ.get('PR_BODY', ''))[0]} "
              f"bump after {args.base_version}, changelog section present")
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
