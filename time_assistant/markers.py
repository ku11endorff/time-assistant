"""Row tags: how time-assistant recognises the rows it wrote in a target.

Every row written to a target carries a tag such as "[ta:t:7000001]" ("t" = time,
"e" = expense, then the entry's id in the source system), normally at the end of the
row's comment. Re-runs find rows by this tag and update them instead of creating
duplicates. Rows without a tag were typed by hand and are never changed.

Versions before targets became pluggable wrote "[kleer:t:<id>]". Those tags are still
recognised, and a row is not rewritten only to change its tag.
"""
from __future__ import annotations

import re

PREFIX = "ta"
LEGACY_PREFIXES = ("kleer",)
TAGS = {"time": "t", "expense": "e"}

# Source ids must fit inside a tag; week.validate_week enforces this.
ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")
_TAG_RE = re.compile(r"\[(%s):([te]):([A-Za-z0-9_-]+)\]"
                     % "|".join(map(re.escape, (PREFIX,) + LEGACY_PREFIXES)))


def tag(kind: str, key) -> str:
    """The tag for one source entry, e.g. tag("time", 7000001) -> "[ta:t:7000001]"."""
    return f"[{PREFIX}:{TAGS[kind]}:{key}]"


def append(text: str | None, kind: str, key) -> str:
    """Text with the entry's tag at the end ("Taxi [ta:e:5-1]", or just the tag)."""
    text = (text or "").strip()
    return f"{text} {tag(kind, key)}".strip()


def find(text: str | None, kind: str) -> str | None:
    """The source id in text's tag, if text carries a tag of this kind; else None."""
    m = _TAG_RE.search(text or "")
    return m.group(3) if m and m.group(2) == TAGS[kind] else None


def normalise(text: str | None) -> str:
    """Text with any legacy tag rewritten to the current prefix, for comparisons."""
    return _TAG_RE.sub(lambda m: f"[{PREFIX}:{m.group(2)}:{m.group(3)}]", (text or "").strip())
