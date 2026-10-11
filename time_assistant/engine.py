"""The part of a run that is the same for every target.

    week file -> approval gate -> per target: pick its projects -> split by month
              -> compare with what the target has -> dry run / write -> verify

Nothing in here knows about a specific target; that lives in time_assistant/targets/.
"""
from __future__ import annotations

import datetime
import os
import time
from dataclasses import dataclass, field

from . import config as conf
from . import targets as registry

OPS = ("create", "update", "delete", "receipt", "skip", "warn")
VERB = {"create": "CREATE", "update": "UPDATE", "delete": "DELETE",
        "receipt": "ATTACH", "skip": "ok    ", "warn": "WARN  "}


@dataclass
class Action:
    op: str                  # create | update | delete | receipt | skip | warn
    kind: str                # time | expense
    key: str                 # the entry's id in the source system
    detail: str
    wanted: object = None    # targets.Wanted, for create/update
    existing: object = None  # targets.Existing, for update/delete/skip and known receipt rows
    path: str | None = None  # receipt file


@dataclass
class Plan:
    """What should happen in one target for one period (a whole week, or one month of it)."""
    target: str = ""
    month: str | None = None
    d_from: str = ""
    d_to: str = ""
    actions: list = field(default_factory=list)
    errors: list = field(default_factory=list)

    def add(self, op, kind, key, detail, **kw):
        self.actions.append(Action(op, kind, str(key), detail, **kw))

    def count(self) -> dict:
        return {op: sum(1 for a in self.actions if a.op == op) for op in OPS}


def _entries(n: int) -> str:
    return f"{n} time entr{'y' if n == 1 else 'ies'}"


# --------------------------------------------------------------------------------------
# approval
# --------------------------------------------------------------------------------------
def unapproved(entries, statuses) -> list[dict]:
    """Entries whose status is not one of statuses. A missing status counts as not approved."""
    ok = {str(s).strip().lower() for s in statuses}
    return [e for e in entries if str(e.get("status") or "").strip().lower() not in ok]


def approval_errors(cfg, week) -> list[str]:
    """The week may only be replicated once the source shows it as approved.

    Looks at EVERY time entry of the week (any project), because approval is a property
    of the reported week, and blocks every target.
    """
    if not conf.approval_required(cfg):
        return []
    bad = unapproved(week.get("time_events", []), conf.accepted_statuses(cfg))
    if not bad:
        return []
    src = conf.source_name(cfg)
    days = ", ".join(sorted({e["date"] for e in bad}))
    errs = [f"WEEK NOT APPROVED IN {src.upper()}: {_entries(len(bad))} ({days}) not approved yet. "
            f"The week has not yet been approved in {src} and therefore cannot be replicated "
            f"to any target. Approve the week in {src}, then {conf.rerun_hint(cfg)}."]
    errs += [f"  - {e['date']} #{e['id']} {e.get('hours')} h, status {e.get('status') or 'missing'}"
             for e in bad]
    return errs


def target_approval_errors(cfg, tcfg, entries) -> list[str]:
    """A target may accept fewer statuses than the week gate (e.g. only Certified)."""
    statuses = tcfg.get("accepted_statuses")
    if not statuses:
        return []
    bad = unapproved(entries, statuses)
    if not bad:
        return []
    days = ", ".join(sorted({e["date"] for e in bad}))
    return [f"target '{tcfg['name']}' only takes entries with status {' or '.join(statuses)}: "
            f"{_entries(len(bad))} ({days}) do not have it yet in {conf.source_name(cfg)}. "
            f"Run again once they do, or leave this target out with --target."]


# --------------------------------------------------------------------------------------
# routing and periods
# --------------------------------------------------------------------------------------
def route(week, project_ids) -> dict:
    """The part of the week that belongs to the given source projects."""
    ids = set(project_ids)
    out = dict(week)
    out["time_events"] = [e for e in week.get("time_events", []) if e.get("project_id") in ids]
    out["expenses"] = [x for x in week.get("expenses", []) if x.get("project_id") in ids]
    return out


def not_routed(week, tcfgs) -> list[str]:
    """Entries that none of the given targets takes, for the report at the end."""
    ids = {p for t in tcfgs for p in t.get("source_project_ids", [])}
    out = [f"{e['date']} time #{e['id']} ({e.get('hours')} h, project {e.get('project_id')})"
           for e in week.get("time_events", []) if e.get("project_id") not in ids]
    out += [f"{x['date']} expense #{x['id']} ({x.get('description', '')!r}, project {x.get('project_id')})"
            for x in week.get("expenses", []) if x.get("project_id") not in ids]
    return out


def split_by_month(week) -> list[dict]:
    """Split a week into one part per calendar month it touches.

    A week that runs 28 Sep - 4 Oct becomes [28-30 Sep] and [1-4 Oct], each planned,
    written and read back on its own, so a closed month (or a failure in one month)
    can never block or corrupt the other.
    """
    d0 = datetime.date.fromisoformat(week["from"])
    d1 = datetime.date.fromisoformat(week["to"])
    segs, cur = [], d0
    while cur <= d1:
        nxt = (cur.replace(day=28) + datetime.timedelta(days=4)).replace(day=1)  # 1st of next month
        end = min(d1, nxt - datetime.timedelta(days=1))
        ym = cur.strftime("%Y-%m")
        seg = dict(week)
        seg["from"], seg["to"] = cur.isoformat(), end.isoformat()
        seg["month"] = ym
        seg["time_events"] = [e for e in week.get("time_events", []) if e["date"][:7] == ym]
        seg["expenses"] = [x for x in week.get("expenses", []) if x["date"][:7] == ym]
        segs.append(seg)
        cur = end + datetime.timedelta(days=1)
    return segs


# --------------------------------------------------------------------------------------
# planning one target
# --------------------------------------------------------------------------------------
def time_mapping(tcfg, item):
    """The time_map entry for an entry's activity; a specific entry wins over the default."""
    best = None
    for m in tcfg.get("time_map", []):
        if "source_activity_id" in m and m["source_activity_id"] != item.get("activity_id"):
            continue
        if best is None or ("source_activity_id" in m and "source_activity_id" not in best):
            best = m
    return best


def expense_mapping(tcfg, item):
    emap = tcfg.get("expense_map") or {}
    return emap.get(item.get("expense_type")) or emap.get("default")


def takes_expenses(tcfg) -> bool:
    """Expenses are opt-in per target: without an expense_map they are listed, not written."""
    return any(not k.startswith("_") for k in (tcfg.get("expense_map") or {}))


def _icloud_hint(path: str) -> str:
    """iCloud keeps not-yet-downloaded files as hidden '.<name>.icloud' placeholders."""
    d, n = os.path.split(path)
    if os.path.exists(os.path.join(d, f".{n}.icloud")):
        return (" (it is in iCloud but not downloaded to this Mac - open the folder in Finder "
                "and click the cloud icon, or run `brctl download <path>`)")
    return ""


def build_plan(target, tcfg, seg, allow_missing_receipts=False) -> Plan:
    """Plan one period (seg: a routed week or one month of it) for one connected target."""
    plan = Plan(target=tcfg["name"], month=seg.get("month"), d_from=seg["from"], d_to=seg["to"])
    want = {"time": {}, "expense": {}}
    for ev in seg.get("time_events", []):
        m = time_mapping(tcfg, ev)
        if m is None:
            plan.errors.append(f"time entry #{ev['id']} ({ev['date']}, activity {ev.get('activity_id')}) "
                               f"has no mapping in time_map of target '{tcfg['name']}'")
            continue
        want["time"][str(ev["id"])] = (ev, target.build("time", ev, m))
    kinds = ["time"]
    if target.supports_expenses:
        kinds.append("expense")
        for ex in seg.get("expenses", []):
            m = expense_mapping(tcfg, ex)
            if m is None:
                plan.errors.append(f"expense #{ex['id']} ({ex['date']}, type {ex.get('expense_type')!r}) "
                                   f"has no mapping in expense_map of target '{tcfg['name']}'")
                continue
            want["expense"][str(ex["id"])] = (ex, target.build("expense", ex, m))

    # Never delete based on an incomplete mapping: a "stale" row might just be an unmapped one.
    delete_stale = bool(tcfg.get("delete_stale", False)) and not plan.errors
    have = {}
    for kind in kinds:
        have[kind] = target.existing(kind, seg["from"], seg["to"])
        diff(plan, target, kind, want[kind], have[kind], delete_stale)
    if target.supports_expenses:
        plan_receipts(plan, target, want["expense"], have["expense"], allow_missing_receipts)
    return plan


def diff(plan: Plan, target, kind, wanted: dict, existing: list, delete_stale: bool):
    by_key, manual = {}, []
    for row in existing:
        if row.key:
            by_key[row.key] = row
        else:
            manual.append(row)

    for key, (item, w) in wanted.items():
        have = by_key.get(key)
        label = f"{item['date']} {kind} #{key}"
        if have is None:
            plan.add("create", kind, key, label, wanted=w)
            for row in manual:   # possible double entry typed by hand
                if row.date == item["date"] and row.project == w.project:
                    plan.add("warn", kind, key,
                             f"{item['date']}: {target.display_name} already has a {kind} row typed "
                             f"by hand (id {row.id}) on the same project and day - check for a double entry")
                    break
        elif target.same(kind, have, w):
            plan.add("skip", kind, key, label + " (unchanged)", existing=have)
        else:
            plan.add("update", kind, key, label, wanted=w, existing=have)

    for key, have in by_key.items():
        if key not in wanted:
            msg = (f"{have.date} {kind} #{key} is in {target.display_name} (id {have.id}) but no longer "
                   f"in the source for this target"
                   + ("" if delete_stale else " - kept; set delete_stale to true to remove it"))
            plan.add("delete" if delete_stale else "warn", kind, key, msg, existing=have)


def plan_receipts(plan: Plan, target, wanted_exp: dict, existing_exp: list, allow_missing: bool):
    """Every replicated expense with a receipt in the source needs a local file to attach."""
    rows = {r.key: r for r in existing_exp if r.key}
    for key, (ex, _) in wanted_exp.items():
        if not ex.get("has_receipt"):
            continue
        label = f"{ex['date']} expense #{key} receipt"
        if not target.supports_receipts:
            plan.add("warn", "expense", key,
                     f"{label} not attached: {target.display_name} does not take receipt files")
            continue
        path = ex.get("receipt_file")
        if not path:
            msg = (f"{ex['date']} expense #{key} ({ex.get('description', '')!r}, "
                   f"{ex['amount_ore'] / 100:.2f}) has a receipt in the source but no receipt_file "
                   f"was given")
            if allow_missing:
                plan.add("warn", "expense", key, msg + " - continuing without receipt")
            else:
                plan.errors.append(msg + " (use --allow-missing-receipts to skip)")
            continue
        path = os.path.expanduser(path)
        if not os.path.isfile(path):
            plan.errors.append(f"{label}: file not found: {path}{_icloud_hint(path)}")
            continue
        name = os.path.basename(path)
        row = rows.get(key)
        if row is not None and name.lower() in [n.lower() for n in target.attached_files(row)]:
            plan.add("skip", "expense", key, label + f" ({name} already attached)", existing=row)
            continue
        plan.add("receipt", "expense", key, label + f" <- {name}", existing=row, path=path)


def plan_target(cfg, tcfg, target, week, allow_missing_receipts=False) -> list[Plan]:
    """All plans (one per month, if the target splits by month) for one connected target."""
    routed = route(week, tcfg["source_project_ids"])
    gate = Plan(target=tcfg["name"], d_from=week["from"], d_to=week["to"])
    gate.errors += target_approval_errors(cfg, tcfg, routed["time_events"])
    if not target.supports_expenses:
        for x in routed["expenses"]:
            gate.add("warn", "expense", x["id"], f"{x['date']} expense #{x['id']} not replicated: "
                     f"{target.display_name} does not take expenses")
    elif not takes_expenses(tcfg):
        for x in routed["expenses"]:
            gate.add("warn", "expense", x["id"], f"{x['date']} expense #{x['id']} not replicated: "
                     f"target '{tcfg['name']}' has no expense_map")
        routed["expenses"] = []
    if gate.errors:
        return [gate]
    segs = split_by_month(routed) if target.split_by_month else [dict(routed, month=None)]
    plans = [gate] if gate.actions else []
    for seg in segs:
        try:
            plans.append(build_plan(target, tcfg, seg, allow_missing_receipts))
        except SystemExit as e:     # e.g. the target could not be read: report, keep going
            p = Plan(target=tcfg["name"], month=seg.get("month"), d_from=seg["from"], d_to=seg["to"])
            p.errors.append(f"could not read {target.display_name}: {e}")
            plans.append(p)
    return plans


# --------------------------------------------------------------------------------------
# writing
# --------------------------------------------------------------------------------------
def execute(plan: Plan, target):
    fresh = None   # source id -> expense row, read once after creates
    for a in plan.actions:
        if a.op == "create":
            target.create(a.kind, a.wanted)
        elif a.op == "update":
            target.update(a.kind, a.existing, a.wanted)
        elif a.op == "delete":
            target.delete(a.kind, a.existing)
        elif a.op == "receipt":
            row = a.existing
            if row is None:
                if fresh is None:
                    fresh = {r.key: r for r in target.existing("expense", plan.d_from, plan.d_to) if r.key}
                row = fresh.get(a.key)
            if row is None:
                raise SystemExit(f"Cannot attach receipt: expense #{a.key} not found in "
                                 f"{target.display_name} after creating it.")
            target.attach_receipt(row, a.path)
        else:
            continue
        if target.write_pause:
            time.sleep(target.write_pause)   # be gentle with rate limits


# --------------------------------------------------------------------------------------
# output
# --------------------------------------------------------------------------------------
def print_plan(plan: Plan):
    for a in plan.actions:
        print(f"  {VERB[a.op]}  {a.detail}")
    for e in plan.errors:
        print(f"  ERROR   {e}")


def totals(plans) -> dict:
    c = {op: 0 for op in OPS}
    for p in plans:
        for op, n in p.count().items():
            c[op] += n
    c["errors"] = sum(len(p.errors) for p in plans)
    return c


def counts_text(plans) -> str:
    c = totals(plans)
    return (f"{c['create']} create, {c['update']} update, {c['delete']} delete, "
            f"{c['receipt']} receipts, {c['skip']} unchanged, {c['warn']} warnings, {c['errors']} errors")


def summary_line(plans, applied: bool) -> str:
    # Sync.command looks for "dry run - nothing written: 0 create, 0 update, 0 delete, 0 receipts"
    # at the start of a line; keep this format.
    return f"{'applied' if applied else 'dry run - nothing written'}: {counts_text(plans)}"


def _month_header(plan, n_segs, applied):
    if plan.month and n_segs > 1:
        extra = "" if applied else " (handled separately)"
        print(f"--- Month {plan.month}: {plan.d_from} .. {plan.d_to}{extra} ---")


# --------------------------------------------------------------------------------------
# a whole run
# --------------------------------------------------------------------------------------
def run(cfg, week, connect, names=None, apply=False, allow_missing_receipts=False) -> int:
    """Plan (and with apply=True, write) the week for the selected targets.

    connect(tcfg) returns a connected Target; it is a parameter so tests can pass fakes.
    Returns the exit code; raises SystemExit with a message when nothing may be written.
    """
    print(f"Week {week.get('week', '?')}  {week['from']} .. {week['to']}\n")

    gate = approval_errors(cfg, week)   # whole week, every target, before anything is read
    if gate:
        for e in gate:
            print(f"  ERROR   {e}")
        if apply:
            raise SystemExit(f"\nNothing was written: the week is not approved in {conf.source_name(cfg)}.")
        return 1

    tcfgs = conf.select_targets(cfg, names)
    if not tcfgs:
        raise SystemExit("No enabled targets in config.json (or name one with --target).")
    runs = []   # (tcfg, target, plans)
    for tcfg in tcfgs:
        cls = registry.TARGETS.get(tcfg["type"])
        label = f"{tcfg['name']} ({cls.display_name if cls else tcfg['type']})"
        try:
            target = connect(tcfg)
        except SystemExit as e:
            p = Plan(target=tcfg["name"], d_from=week["from"], d_to=week["to"])
            p.errors.append(f"cannot connect: {e}")
            target, plans = None, [p]
        else:
            plans = plan_target(cfg, tcfg, target, week, allow_missing_receipts)
        runs.append((tcfg, label, target, plans))
        if not apply:
            print(f"=== {label} ===")
            n_segs = sum(1 for p in plans if p.month)
            for p in plans:
                _month_header(p, n_segs, applied=False)
                print_plan(p)
            print(f"  -> {counts_text(plans)}\n")

    left_out = not_routed(week, tcfgs)
    all_plans = [p for _, _, _, plans in runs for p in plans]
    errors = sum(len(p.errors) for p in all_plans)

    if apply and errors:
        for _, label, _, plans in runs:
            print(f"=== {label} ===")
            for p in plans:
                print_plan(p)
        clean = [t["name"] for t, _, _, plans in runs if not any(p.errors for p in plans)]
        hint = (f" To write only the targets without errors: --target {' --target '.join(clean)}"
                if clean and len(clean) < len(runs) else "")
        raise SystemExit(f"\nRefusing to apply while there are errors. Nothing was written. "
                         f"Fix them first.{hint}")

    failed = []
    if apply:
        for tcfg, label, target, plans in runs:
            print(f"=== {label} ===")
            n_segs = sum(1 for p in plans if p.month)
            for p in plans:
                _month_header(p, n_segs, applied=True)
                try:
                    execute(p, target)
                    print_plan(p)
                except (SystemExit, Exception) as e:   # one target/month failing must not block the others
                    where = f"{tcfg['name']}" + (f" month {p.month}" if p.month else "")
                    failed.append(where)
                    print(f"  FAILED  {where}: {e}")
            print(f"  -> {counts_text(plans)}\n")

    if left_out:
        print(f"Not replicated to any target ({len(left_out)} items outside every target's "
              f"source_project_ids):")
        for i in left_out:
            print(f"    - {i}")
        print()
    print(summary_line(all_plans, applied=apply))
    if failed:
        raise SystemExit(f"\nNot fully written: {', '.join(failed)}. Everything else was still "
                         f"processed. Fix the problem and run the same week again; rows already "
                         f"written are updated, never duplicated.")
    return 1 if errors else 0
