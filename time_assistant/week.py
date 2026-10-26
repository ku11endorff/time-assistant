"""The week file: the contract between the agent (or a person) and sync.py.

Shape: schema/week.schema.json. Procedure for producing it: docs/agent-playbook.md.
"""
from __future__ import annotations

import datetime
import json

from . import markers

# Version of docs/agent-playbook.md. The agent copies it into every week file, so a week
# exported with outdated instructions is noticed. Bump it whenever the playbook changes
# what the agent writes, and update the number in the playbook (tests check they match).
#   1 single TimeKeeper   2 targets   3 daily allowances   4 playbook_version in the file
#   5 vat_ore, allowance quantity (half days), expense project ids, foreign currency, receipts
#     fetched from the source in cloud sessions
PLAYBOOK_VERSION = 5

EXPENSE_KINDS = ("receipt", "allowance")
ALLOWANCE_TYPES = ("domestic", "foreign")   # inrikes / utrikes traktamente


def is_allowance(item: dict) -> bool:
    return item.get("kind", "receipt") == "allowance"


def playbook_notice(week: dict) -> str | None:
    """A warning when the week file was made with other agent instructions than this
    version expects; None when they match."""
    v = week.get("playbook_version")
    if v is None:
        return ("this week file has no playbook_version: your agent follows instructions from "
                "before time-assistant 0.4.0 and may leave out newer data, such as daily "
                "allowances. Refresh its instructions (docs/updating.md).")
    if not isinstance(v, int) or isinstance(v, bool):
        return None   # reported by validate_week
    if v < PLAYBOOK_VERSION:
        return (f"this week file was made with agent playbook {v}, but this version of "
                f"time-assistant uses playbook {PLAYBOOK_VERSION}. Refresh your agent's "
                f"instructions (docs/updating.md); CHANGELOG.md says what changed.")
    if v > PLAYBOOK_VERSION:
        return (f"this week file was made with agent playbook {v}, newer than this "
                f"time-assistant (playbook {PLAYBOOK_VERSION}). Update time-assistant "
                f"(docs/updating.md).")
    return None


def load(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _is_date(v) -> bool:
    try:
        datetime.date.fromisoformat(str(v))
        return len(str(v)) == 10
    except ValueError:
        return False


def validate_week(week) -> list[str]:
    """Check that a week file has the documented shape (see schema/week.schema.json).

    Meant to catch mistakes made by whichever agent produced the file, before any
    target is contacted. Returns a list of problems (empty = valid).
    """
    errs: list[str] = []
    if not isinstance(week, dict):
        return ["week file must be a JSON object"]
    for k in ("from", "to"):
        if not _is_date(week.get(k)):
            errs.append(f"'{k}' must be a date like 2026-10-05")
    if _is_date(week.get("from")) and _is_date(week.get("to")) and week["from"] > week["to"]:
        errs.append("'from' is after 'to'")
    for k in ("time_events", "expenses"):
        if not isinstance(week.get(k), list):
            errs.append(f"'{k}' must be a list (use [] when empty)")
    pv = week.get("playbook_version")
    if pv is not None and (isinstance(pv, bool) or not isinstance(pv, int)):
        errs.append("'playbook_version' must be a whole number, copied from the agent playbook")
    rng = (week.get("from"), week.get("to"))

    def in_range(d):
        return not (_is_date(rng[0]) and _is_date(rng[1])) or rng[0] <= d <= rng[1]

    def check_common(w, x, seen):
        if x.get("id") in (None, ""):
            errs.append(f"{w}: 'id' is required")
        elif isinstance(x["id"], bool) or not markers.ID_RE.match(str(x["id"])):
            errs.append(f"{w}: 'id' may only contain letters, digits, '-' and '_'")
        elif x["id"] in seen:
            errs.append(f"{w}: duplicate id {x['id']}")
        else:
            seen.add(x["id"])
        if not _is_date(x.get("date")):
            errs.append(f"{w}: 'date' must be yyyy-mm-dd")
        elif not in_range(x["date"]):
            errs.append(f"{w}: date {x['date']} is outside from/to")
        if "project_id" not in x or not (x["project_id"] is None or
                                         (isinstance(x["project_id"], int)
                                          and not isinstance(x["project_id"], bool))):
            errs.append(f"{w}: 'project_id' must be an integer or null")

    seen: set = set()
    for i, e in enumerate(week.get("time_events") or []):
        w = f"time_events[{i}]"
        if not isinstance(e, dict):
            errs.append(f"{w} must be an object")
            continue
        check_common(w, e, seen)
        h = e.get("hours")
        if isinstance(h, bool) or not isinstance(h, (int, float)) or not 0 < h <= 24:
            errs.append(f"{w}: 'hours' must be a number between 0 and 24 (decimal hours, e.g. 7.5)")
        if isinstance(e.get("activity_id"), bool) or not isinstance(e.get("activity_id"), int):
            errs.append(f"{w}: 'activity_id' must be an integer")
        if not isinstance(e.get("status"), str) or not e["status"]:
            errs.append(f"{w}: 'status' is required (copy the source system's approval status)")
        if "comment" in e and not isinstance(e["comment"], str):
            errs.append(f"{w}: 'comment' must be a string")
    seen = set()
    for i, x in enumerate(week.get("expenses") or []):
        w = f"expenses[{i}]"
        if not isinstance(x, dict):
            errs.append(f"{w} must be an object")
            continue
        check_common(w, x, seen)
        a = x.get("amount_ore")
        if isinstance(a, bool) or not isinstance(a, int) or a < 0:
            errs.append(f"{w}: 'amount_ore' must be a non-negative integer "
                        f"(amount incl. VAT in 1/100 currency units)")
        if not isinstance(x.get("has_receipt", False), bool):
            errs.append(f"{w}: 'has_receipt' must be true or false")
        v = x.get("vat_ore")
        if v is not None and (isinstance(v, bool) or not isinstance(v, int) or v < 0):
            errs.append(f"{w}: 'vat_ore' must be a non-negative integer (the VAT part of "
                        f"amount_ore, in 1/100 currency units)")
        kind = x.get("kind", "receipt")
        if kind not in EXPENSE_KINDS:
            errs.append(f"{w}: 'kind' must be \"receipt\" or \"allowance\"")
        elif kind == "allowance":
            if x.get("allowance_type") not in ALLOWANCE_TYPES:
                errs.append(f"{w}: an allowance needs 'allowance_type' \"domestic\" (inrikes) "
                            f"or \"foreign\" (utrikes)")
            if x.get("has_receipt"):
                errs.append(f"{w}: an allowance has no receipt; set 'has_receipt' to false")
        q = x.get("quantity")
        if q is not None:
            if kind != "allowance":
                errs.append(f"{w}: 'quantity' is only for allowances (1 = full day, 0.5 = half day)")
            elif isinstance(q, bool) or not isinstance(q, (int, float)) or not 0 < q <= 1:
                errs.append(f"{w}: 'quantity' must be a number above 0 and at most 1 "
                            f"(1 = full day, 0.5 = half day)")
    return errs
