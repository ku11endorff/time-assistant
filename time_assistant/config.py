"""config.json: which targets receive which source projects, and how ids map.

Template: config.example.json. Field reference: docs/configuration.md. Keys starting
with "_" are notes for people and are ignored.
"""
from __future__ import annotations

import json
import re

from . import targets as registry
from .week import ALLOWANCE_TYPES

VERSION = 2
DEFAULT_ACCEPTED_STATUSES = ("Approved", "Certified")   # Kleer: approved / certified
DEFAULT_SOURCE_NAME = "the source system"
# What to do after approving; override per person with source.rerun_hint
# (e.g. the name of the skill or command that runs your export).
DEFAULT_RERUN_HINT = "run the export again"
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


# --------------------------------------------------------------------------------------
# loading
# --------------------------------------------------------------------------------------
def read(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            cfg = json.load(f)
    except FileNotFoundError:
        raise SystemExit(f"{path} not found. Copy config.example.json to {path} and fill in "
                         f"your own ids (docs/configuration.md).") from None
    except json.JSONDecodeError as e:
        raise SystemExit(f"{path} is not valid JSON ({e}). Look for curly quotes or a missing "
                         f"comma; config.example.json shows the expected shape.") from None
    if is_legacy(cfg):
        raise SystemExit(f"{path} uses the old single-TimeKeeper format. Convert it once with\n"
                         f"  python3 sync.py --config {path} migrate-config\n"
                         f"(a backup of the old file is kept).")
    return cfg


def load(path: str) -> dict:
    """Read and fully check config.json; exits with every problem listed if it is not usable."""
    cfg = read(path)
    problems = check(cfg)
    if problems:
        raise SystemExit(f"{path} has {len(problems)} problem(s):\n"
                         + "\n".join(f"  ERROR   {p}" for p in problems))
    return cfg


def is_legacy(cfg) -> bool:
    return isinstance(cfg, dict) and "targets" not in cfg and (
        "scope" in cfg or "timekeeper_user_id" in cfg)


# --------------------------------------------------------------------------------------
# accessors
# --------------------------------------------------------------------------------------
def source_name(cfg) -> str:
    return str((cfg.get("source") or {}).get("name") or DEFAULT_SOURCE_NAME)


def rerun_hint(cfg) -> str:
    hint = str((cfg.get("source") or {}).get("rerun_hint") or "").strip().rstrip(".")
    return hint or DEFAULT_RERUN_HINT


def approval_required(cfg) -> bool:
    return (cfg.get("approval") or {}).get("required", True) is not False


def accepted_statuses(cfg) -> tuple:
    return tuple((cfg.get("approval") or {}).get("accepted_statuses") or DEFAULT_ACCEPTED_STATUSES)


def enabled(tcfg) -> bool:
    return tcfg.get("enabled", True) is not False


def select_targets(cfg, names=None) -> list[dict]:
    """The targets to run: the named ones, or every enabled one."""
    all_t = cfg.get("targets") or []
    if not names:
        return [t for t in all_t if enabled(t)]
    by_name = {t.get("name"): t for t in all_t}
    unknown = [n for n in names if n not in by_name]
    if unknown:
        raise SystemExit(f"Unknown target(s): {', '.join(unknown)}. Targets in config.json: "
                         f"{', '.join(str(n) for n in by_name)}.")
    return [by_name[n] for n in dict.fromkeys(names)]


# --------------------------------------------------------------------------------------
# checking
# --------------------------------------------------------------------------------------
def _is_int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _missing(v) -> bool:
    return v is None or v == ""


def check(cfg) -> list[str]:
    """Every problem in config.json, without contacting any target."""
    if not isinstance(cfg, dict):
        return ["config.json must be a JSON object"]
    p: list[str] = []
    if cfg.get("version") != VERSION:
        p.append(f"'version' must be {VERSION}")
    src = cfg.get("source", {})
    if not isinstance(src, dict):
        p.append("'source' must be an object")
    ap = cfg.get("approval", {})
    if not isinstance(ap, dict):
        p.append("'approval' must be an object")
    elif "accepted_statuses" in ap and not _str_list(ap["accepted_statuses"]):
        p.append("approval.accepted_statuses must be a non-empty list of status names")

    tl = cfg.get("targets")
    if not isinstance(tl, list) or not tl:
        p.append("'targets' must be a non-empty list (see config.example.json)")
        return p
    names, identities = set(), {}
    for i, t in enumerate(tl):
        if not isinstance(t, dict):
            p.append(f"targets[{i}] must be an object")
            continue
        name = t.get("name")
        w = f"target {name!r}" if isinstance(name, str) and name else f"targets[{i}]"
        if not isinstance(name, str) or not NAME_RE.match(name):
            p.append(f"{w}: 'name' must be lowercase letters, digits, '-' or '_' (e.g. \"client\")")
        elif name in names:
            p.append(f"{w}: the name is used twice")
        names.add(name)
        cls = registry.TARGETS.get(t.get("type"))
        if cls is None:
            p.append(f"{w}: unknown 'type' {t.get('type')!r}; available: "
                     f"{', '.join(sorted(registry.TARGETS))}")
            continue
        p += [f"{w}: {x}" for x in check_target(t, cls)]
        ident = cls.identity(t)
        if ident is not None:
            key = (cls.type, ident)
            if key in identities:
                p.append(f"{w}: writes to the same {cls.display_name} account and project as "
                         f"target {identities[key]!r}; the two would overwrite each other's rows")
            else:
                identities[key] = name
    return p


def _str_list(v) -> bool:
    return isinstance(v, list) and bool(v) and all(isinstance(x, str) and x for x in v)


def check_target(t: dict, cls) -> list[str]:
    p: list[str] = []
    ids = t.get("source_project_ids")
    if not isinstance(ids, list) or not ids or not all(_is_int(x) for x in ids):
        p.append("'source_project_ids' must be a non-empty list of source project ids (numbers)")
    for k in ("enabled", "delete_stale"):
        if k in t and not isinstance(t[k], bool):
            p.append(f"'{k}' must be true or false")
    if "accepted_statuses" in t and not _str_list(t["accepted_statuses"]):
        p.append("'accepted_statuses' must be a non-empty list of status names")
    if cls.needs_username and (not isinstance(t.get("username"), str) or not t["username"].strip()):
        p.append(f"'username' is required (your {cls.display_name} login name; it is not a secret)")
    s = t.get("settings", {})
    if not isinstance(s, dict):
        p.append("'settings' must be an object")
        s = {}
    for k in cls.required_settings:
        if _missing(s.get(k)):
            p.append(f"settings.{k} is required")

    tm = t.get("time_map")
    if not isinstance(tm, list) or not tm:
        p.append("'time_map' needs at least one entry")
        tm = []
    seen = set()
    for j, m in enumerate(tm):
        mw = f"time_map[{j}]"
        if not isinstance(m, dict):
            p.append(f"{mw} must be an object")
            continue
        sa = m.get("source_activity_id", "default")
        if sa != "default" and not _is_int(sa):
            p.append(f"{mw}: source_activity_id must be a number (leave it out for a default entry)")
        if sa in seen:
            p.append(f"{mw}: more than one default entry" if sa == "default"
                     else f"{mw}: source activity {sa} is mapped twice")
        seen.add(sa)
        for k in cls.time_map_fields:
            if _missing(m.get(k)):
                p.append(f"{mw}: '{k}' is required")

    em = t.get("expense_map", {})
    if not isinstance(em, dict):
        p.append("'expense_map' must be an object: source expense type (or \"default\") -> mapping")
    elif cls.supports_expenses:
        for typ, m in em.items():
            if typ.startswith("_"):
                continue
            if not isinstance(m, dict):
                p.append(f"expense_map[{typ!r}] must be an object")
                continue
            for k in cls.expense_map_fields:
                if _missing(m.get(k)):
                    p.append(f"expense_map[{typ!r}]: '{k}' is required")

    am = t.get("allowance_map")
    if am is not None:
        if not isinstance(am, dict):
            p.append("'allowance_map' must be an object: \"domestic\" / \"foreign\" -> mapping")
        elif not cls.supports_allowances:
            p.append(f"'allowance_map' is set, but {cls.display_name} does not take allowances")
        else:
            for typ, m in am.items():
                if typ.startswith("_"):
                    continue
                if typ not in ALLOWANCE_TYPES:
                    p.append(f"allowance_map: unknown type {typ!r}; use \"domestic\" or \"foreign\"")
                elif not isinstance(m, dict):
                    p.append(f"allowance_map[{typ!r}] must be an object")
                else:
                    for k in cls.expense_map_fields:
                        if _missing(m.get(k)):
                            p.append(f"allowance_map[{typ!r}]: '{k}' is required")
    return p + list(cls.check_settings(t))


# --------------------------------------------------------------------------------------
# optional features not in use
# --------------------------------------------------------------------------------------
def _keys(d) -> set:
    return {k for k in (d or {}) if not k.startswith("_")}


def feature_notes(cfg) -> list[str]:
    """Optional features a target supports but this config does not use. Shown by
    check-config so that people who update learn what they could switch on; never errors.
    A new optional config key should add its note here (CONTRIBUTING.md)."""
    notes = []
    for t in cfg.get("targets") or []:
        cls = registry.TARGETS.get(t.get("type"))
        if cls is None or not isinstance(t, dict):
            continue
        name = t.get("name")
        if cls.supports_expenses and not _keys(t.get("expense_map")):
            notes.append(f"target '{name}': no expense_map, so expenses are listed but not "
                         f"written (docs/configuration.md#expense_map)")
        if cls.supports_allowances:
            missing = [a for a in ALLOWANCE_TYPES if a not in _keys(t.get("allowance_map"))]
            if len(missing) == len(ALLOWANCE_TYPES):
                notes.append(f"target '{name}': can take daily allowances (traktamente, new in "
                             f"0.3.0); add an allowance_map to replicate them "
                             f"(docs/configuration.md#allowance_map)")
            elif missing:
                notes.append(f"target '{name}': no allowance_map entry for "
                             f"{' or '.join(missing)} allowances; those are listed but not written")
    return notes


# --------------------------------------------------------------------------------------
# converting the old format
# --------------------------------------------------------------------------------------
def _rename(d: dict, names: dict) -> dict:
    out = {}
    for k, v in d.items():
        out[names.get(k, k)] = v
    return out


def migrate(old: dict, username: str = "") -> dict:
    """Convert the single-TimeKeeper format (version 1) into the current one."""
    ap = dict(old.get("approval") or {})
    source = {"name": "Kleer"}
    if ap.get("rerun_hint"):
        source["rerun_hint"] = ap.pop("rerun_hint")
    scope = old.get("scope") or {}
    settings = {"user_id": old.get("timekeeper_user_id"), "project_id": scope.get("tk_project_id")}
    if scope.get("_tk_name"):
        settings["_project_name"] = scope["_tk_name"]
    target = {
        "name": "timekeeper",
        "type": "timekeeper",
        "username": username or "",
        "source_project_ids": [scope["kleer_project_id"]] if scope.get("kleer_project_id") else [],
    }
    if scope.get("_kleer_name"):
        target["_source_project_name"] = scope["_kleer_name"]
    target["delete_stale"] = bool(old.get("delete_stale", False))
    target["settings"] = settings
    target["time_map"] = [
        _rename({k: v for k, v in m.items()},
                {"kleer_activity_id": "source_activity_id",
                 "_kleer_activity_name": "_source_activity_name",
                 "tk_activity_id": "activity_id", "tk_timecode_id": "timecode_id"})
        for m in old.get("time_map") or []]
    target["expense_map"] = {
        typ: _rename(m, {"tk_wagecode_id": "wagecode_id"}) if isinstance(m, dict) else m
        for typ, m in (old.get("expense_map") or {}).items()}
    new = {"version": VERSION, "source": source}
    if ap:
        new["approval"] = ap
    new["targets"] = [target]
    return new
