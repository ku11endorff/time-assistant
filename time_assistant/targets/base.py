"""The interface every target implements.

A target is one system that should receive copies of the approved week (TimeKeeper,
a client's time tool, a staffing partner's portal, ...). The engine does everything that
is the same for all targets: the approval gate, picking the entries for each target,
the month split, comparing with what the target already has, the dry run and the
output. A target only knows its own API:

    existing()        which rows are already there
    build()           what a source entry should look like there
    same()            whether an existing row already looks like that
    create() / update() / delete()
    attached_files() / attach_receipt()     only if supports_receipts

Rows are recognised by the tag from time_assistant.markers, normally at the end of the
row's comment. See docs/adding-a-target.md for a walkthrough and a skeleton.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .. import markers

KINDS = ("time", "expense")


@dataclass
class Existing:
    """A row that is already in the target."""
    id: object                    # the target's own id for the row
    key: str | None               # source id from the row's tag; None = typed by hand
    date: str                     # yyyy-mm-dd
    project: object = None        # the target's project, used to flag possible double entries
    raw: dict = field(default_factory=dict)   # the row as the target's API returned it


@dataclass
class Wanted:
    """A row as it should look in the target, built from one source entry."""
    payload: dict                 # what create()/update() send
    project: object = None        # the target's project for this row


class Target:
    # ---- description: override these in your subclass ------------------------------
    type = ""                     # the "type" value in config.json, e.g. "timekeeper"
    display_name = ""             # how the target is named in output, e.g. "TimeKeeper"
    supports_expenses = False     # can it store expenses at all?
    supports_receipts = False     # can a receipt file be attached to an expense?
    supports_allowances = False   # can it store daily allowances (traktamente)? They are
                                  # expenses mapped by allowance_map instead of expense_map
    split_by_month = False        # True if the system locks or reports per calendar month
    needs_username = False        # True if config.json must give "username" for the target
    secrets: tuple = ()           # e.g. ("password",) or ("token",); never stored in config.json
    required_settings: tuple = () # keys that must be in the target's "settings"
    time_map_fields: tuple = ()   # keys every time_map entry must have
    expense_map_fields: tuple = ()  # keys every expense_map entry must have
    write_pause = 0.0             # seconds to wait between writes (rate limits)

    def __init__(self, config: dict, secrets: dict | None = None):
        self.config = config
        self.name = config.get("name", self.type)
        self.settings = config.get("settings") or {}

    # ---- offline checks ---------------------------------------------------------------
    @classmethod
    def check_settings(cls, config: dict) -> list[str]:
        """Extra checks of this target's part of config.json, beyond the declared fields."""
        return []

    @classmethod
    def feature_notes(cls, config: dict) -> list[str]:
        """Optional features of this target that its config does not use yet (shown as NOTE
        by check-config, never an error)."""
        return []

    @classmethod
    def identity(cls, config: dict):
        """Where this target's rows live (account + project), or None.

        Two targets with the same identity would write over each other's rows, so the
        config check refuses that.
        """
        return None

    # ---- talking to the system ----------------------------------------------------------
    def discover(self) -> None:
        """Print the ids a person needs to fill in this target's part of config.json."""
        raise NotImplementedError

    def existing(self, kind: str, d_from: str, d_to: str) -> list[Existing]:
        """Rows of this kind already in the target between d_from and d_to (inclusive).

        Return only rows in this target's own scope (its account and project), so two
        targets that share an account never see each other's rows. Use markers.find() to
        fill in Existing.key.
        """
        raise NotImplementedError

    def build(self, kind: str, item: dict, mapping: dict) -> Wanted:
        """The row for one source entry (an item of the week file) and its mapping entry.

        Allowances arrive as kind "expense" with item["kind"] == "allowance" and their
        allowance_map entry as mapping; week.is_allowance(item) tells them apart.
        """
        raise NotImplementedError

    def same(self, kind: str, existing: Existing, wanted: Wanted) -> bool:
        """True if the existing row already matches; compare comments with markers.normalise()."""
        raise NotImplementedError

    def create(self, kind: str, wanted: Wanted) -> None:
        raise NotImplementedError

    def update(self, kind: str, existing: Existing, wanted: Wanted) -> None:
        raise NotImplementedError

    def delete(self, kind: str, existing: Existing) -> None:
        raise NotImplementedError

    def attached_files(self, expense: Existing) -> list[str]:
        """File names already attached to an expense row (only if supports_receipts)."""
        raise NotImplementedError

    def attach_receipt(self, expense: Existing, path: str) -> None:
        """Upload one receipt file to an expense row (only if supports_receipts)."""
        raise NotImplementedError

    # ---- helpers for subclasses -----------------------------------------------------------
    def comment(self, kind: str, item: dict, mapping: dict) -> str:
        """The usual comment text: the source's external comment (time) or description
        (expense), falling back to the mapping's "comment", with the tag appended."""
        if kind == "time":
            text = (item.get("comment") or "").strip() or mapping.get("comment", "")
        else:
            text = item.get("description", "")
        return markers.append(text, kind, item["id"])
