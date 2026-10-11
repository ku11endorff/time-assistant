#!/usr/bin/env python3
"""Print the CHANGELOG.md section of one version, for its GitHub release.

    python3 tools/release_notes.py 0.4.0      # exit 1 if the version is not releasable

Refuses when the version differs from time_assistant.__version__, has no section in
CHANGELOG.md, or its section is still marked Unreleased. The release workflow
(.github/workflows/release.yml) runs this for every pushed v* tag.
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from time_assistant import __version__  # noqa: E402


def section(changelog: str, version: str):
    """(heading line, body) of `## [version] - ...`, or None."""
    m = re.search(rf"^## \[{re.escape(version)}\][^\n]*$", changelog, re.M)
    if not m:
        return None
    nxt = re.search(r"^## \[", changelog[m.end():], re.M)
    body = changelog[m.end(): m.end() + nxt.start()] if nxt else changelog[m.end():]
    return m.group(0), body.strip() + "\n"


def problems(version: str, changelog: str) -> list:
    out = []
    if version != __version__:
        out.append(f"tag {version} does not match time_assistant.__version__ {__version__}")
    found = section(changelog, version)
    if found is None:
        out.append(f"CHANGELOG.md has no '## [{version}] - <date>' section")
    elif "unreleased" in found[0].lower():
        out.append(f"CHANGELOG.md still marks {version} as Unreleased; put the release date in")
    return out


def main(argv) -> int:
    if len(argv) != 1:
        print(__doc__)
        return 2
    version = argv[0].lstrip("v")
    with open(os.path.join(ROOT, "CHANGELOG.md"), encoding="utf-8") as f:
        changelog = f.read()
    errs = problems(version, changelog)
    if errs:
        for e in errs:
            print(f"ERROR   {e}", file=sys.stderr)
        return 1
    sys.stdout.write(section(changelog, version)[1])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
