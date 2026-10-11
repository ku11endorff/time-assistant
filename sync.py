#!/usr/bin/env python3
"""time-assistant: replicate an approved week of time/expense entries into TimeKeeper.

Register once in your source system (reference adapter: Kleer). Any AI agent (Claude,
ChatGPT, Microsoft Copilot, ...) or a person exports the week into a small JSON file
(schema/week.schema.json, procedure in docs/agent-playbook.md). This script validates
it, then diffs it against what is already in TimeKeeper (api2.timekeeper.se) and
creates/updates only what differs.

Commands
  validate --week FILE  Check the week file's structure. No network access.
  discover              Show TimeKeeper projects / activities / time codes so you
                        can fill in config.json.
  plan     --week FILE  Dry run: print what would change. Writes nothing.
  apply    --week FILE  Perform the changes.

Credentials come from environment variables only (never from files or args):
  TK_USER, TK_PASSWORD   TimeKeeper Basic Auth
  TK_BASE                optional, default https://api2.timekeeper.se
(tk.sh fills them from the OS keychain, so the password never sits in a file.)

Idempotency: every row written to TimeKeeper gets a marker such as
"[kleer:t:7000001]" at the end of its comment. Re-running the sync finds rows
by that marker and updates instead of duplicating. Rows without a marker (your
manual TimeKeeper entries) are never modified or deleted.
"""
from __future__ import annotations

import argparse
import base64
import datetime
import json
import mimetypes
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field

MARKER_RE = re.compile(r"\[kleer:([te]):([A-Za-z0-9_-]+)\]")


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def g(d: dict, *names, default=None):
    """Case-insensitive dict lookup (TimeKeeper's casing is not guaranteed)."""
    low = {k.lower(): v for k, v in d.items()}
    for n in names:
        if n.lower() in low:
            return low[n.lower()]
    return default


def extract_items(resp):
    """Pull the row list out of a paged/enveloped response."""
    if isinstance(resp, list):
        return resp
    if isinstance(resp, dict):
        for key in ("data", "items", "results", "value", "rows"):
            v = g(resp, key)
            if isinstance(v, list):
                return v
            if isinstance(v, dict):
                inner = extract_items(v)
                if inner:
                    return inner
    return []


def split_hours(hours: float) -> tuple[int, int]:
    total_min = int(round(hours * 60))
    return total_min // 60, total_min % 60


def marker(kind: str, ident) -> str:
    return f"[kleer:{kind}:{ident}]"


def with_marker(text: str, kind: str, ident) -> str:
    text = (text or "").strip()
    return f"{text} {marker(kind, ident)}".strip()


def find_marker(comment: str | None):
    m = MARKER_RE.search(comment or "")
    return (m.group(1), m.group(2)) if m else None


# --------------------------------------------------------------------------
# TimeKeeper client (stdlib only)
# --------------------------------------------------------------------------
class TimeKeeper:
    def __init__(self, user: str, password: str, base: str = "https://api2.timekeeper.se"):
        self.base = base.rstrip("/")
        token = base64.b64encode(f"{user}:{password}".encode()).decode()
        self.headers = {
            "Authorization": f"Basic {token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def _call(self, method: str, path: str, params: dict | None = None, body=None,
              empty_on_404: bool = False):
        url = f"{self.base}{path}"
        if params:
            url += "?" + urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method, headers=self.headers)
        for attempt in range(3):
            try:
                with urllib.request.urlopen(req, timeout=30) as r:
                    raw = r.read().decode() or "null"
                    return json.loads(raw)
            except urllib.error.HTTPError as e:
                detail = e.read().decode(errors="replace")[:500]
                if e.code == 404 and empty_on_404:
                    # TimeKeeper answers 404 when a registration list is empty for the period.
                    return None
                if e.code in (429, 502, 503, 504) and attempt < 2:
                    time.sleep(2 * (attempt + 1))
                    continue
                raise SystemExit(f"TimeKeeper {method} {path} -> HTTP {e.code}: {detail}")
            except urllib.error.URLError as e:
                if attempt < 2:
                    time.sleep(2)
                    continue
                raise SystemExit(f"Cannot reach TimeKeeper ({e.reason}). Check network/TK_BASE.")

    def paged(self, path: str, params: dict | None = None, page_size: int = 100,
              empty_on_404: bool = False):
        rows, page = [], 0
        while True:
            p = dict(params or {}, PageIndex=page, PageSize=page_size)
            chunk = extract_items(self._call("GET", path, p, empty_on_404=empty_on_404))
            rows.extend(chunk)
            if len(chunk) < page_size:
                return rows
            page += 1

    # reads
    def time_regs(self, user_id, d_from, d_to):
        return self.paged("/api/v1/TimeRegistration",
                          {"UserID": user_id, "FromDate": d_from, "ToDate": d_to},
                          empty_on_404=True)

    def expense_regs(self, user_id, d_from, d_to):
        return self.paged("/api/v1/ExpenseRegistration",
                          {"UserID": user_id, "FromDate": d_from, "ToDate": d_to},
                          empty_on_404=True)

    # receipts
    def expense_files(self, expense_id):
        return self.paged("/api/v1/File/ExpenseRegistrationFile",
                          {"ExpenseRegistrationID": expense_id}, empty_on_404=True)

    def upload_expense_file(self, expense_id, path):
        """multipart/form-data: EntityID + Files (see /api/v1/File/ExpenseRegistrationFile)."""
        boundary = "----kleersync" + str(int(time.time() * 1000))
        fname = os.path.basename(path)
        ctype = mimetypes.guess_type(fname)[0] or "application/octet-stream"
        with open(path, "rb") as f:
            content = f.read()
        crlf = b"\r\n"
        body = b"".join([
            f"--{boundary}".encode(), crlf,
            b'Content-Disposition: form-data; name="EntityID"', crlf, crlf,
            str(expense_id).encode(), crlf,
            f"--{boundary}".encode(), crlf,
            f'Content-Disposition: form-data; name="Files"; filename="{fname}"'.encode(), crlf,
            f"Content-Type: {ctype}".encode(), crlf, crlf,
            content, crlf,
            f"--{boundary}--".encode(), crlf,
        ])
        headers = dict(self.headers)
        headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
        req = urllib.request.Request(f"{self.base}/api/v1/File/ExpenseRegistrationFile",
                                     data=body, method="POST", headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return r.read().decode()
        except urllib.error.HTTPError as e:
            raise SystemExit(f"Receipt upload for expense {expense_id} failed: "
                             f"HTTP {e.code}: {e.read().decode(errors='replace')[:500]}")

    # writes
    def create_time(self, body):   return self._call("POST", "/api/v1/TimeRegistration", body=body)
    def update_time(self, body):   return self._call("PUT", "/api/v1/TimeRegistration", body=body)
    def delete_time(self, id_):    return self._call("DELETE", "/api/v1/TimeRegistration", {"id": id_})
    def create_exp(self, body):    return self._call("POST", "/api/v1/ExpenseRegistration", body=body)
    def update_exp(self, body):    return self._call("PUT", "/api/v1/ExpenseRegistration", body=body)
    def delete_exp(self, id_):     return self._call("DELETE", "/api/v1/ExpenseRegistration", {"id": id_})


# --------------------------------------------------------------------------
# planning
# --------------------------------------------------------------------------
@dataclass
class Action:
    op: str            # create | update | delete | skip | warn
    kind: str          # time | expense
    key: str
    detail: str
    payload: dict | None = None
    tk_id: int | None = None


@dataclass
class Plan:
    actions: list[Action] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    ignored: list[str] = field(default_factory=list)  # outside the project scope
    uid: int | None = None
    d_from: str = ""
    d_to: str = ""

    def add(self, *a, **k):
        self.actions.append(Action(*a, **k))


DEFAULT_APPROVED_STATUSES = ("Approved", "Certified")   # Kleer: approved / certified (certified implies approved)


def check_approval(week, plan: "Plan", cfg=None):
    """The week may only be replicated once Kleer shows it as approved (godkänd).

    Looks at EVERY time event in the week file (any project), because approval is a
    property of the reported week. A missing status counts as not approved (fail closed).
    """
    ap = (cfg or {}).get("approval") or {}
    if ap.get("required", True) is False:     # explicit opt-out in config.json
        return
    ok = {str(x).strip().lower() for x in ap.get("accepted_statuses", DEFAULT_APPROVED_STATUSES)}
    bad = [e for e in week.get("time_events", [])
           if str(e.get("status") or "").strip().lower() not in ok]
    if not bad:
        return
    days = ", ".join(sorted({e["date"] for e in bad}))
    plan.errors.append(
        f"WEEK NOT APPROVED IN KLEER: {len(bad)} time entr{'y' if len(bad) == 1 else 'ies'} "
        f"({days}) not approved yet. The week has not yet been approved in Kleer and "
        f"therefore cannot be replicated to TimeKeeper. Approve the week in Kleer, "
        f"then run /sync-tic-time again.")
    for e in bad:
        plan.errors.append(f"  - {e['date']} kleer:{e['id']} {e.get('hours')} h, "
                           f"status {e.get('status') or 'missing'}")


def get_scope(cfg) -> dict:
    s = cfg.get("scope") or {}
    if not s.get("kleer_project_id") or not s.get("tk_project_id"):
        raise SystemExit("config.json: 'scope' with kleer_project_id and tk_project_id is required "
                         "(only that Kleer project is replicated, into that one TimeKeeper project).")
    return s


def apply_scope(cfg, week, plan: "Plan"):
    """Keep only Kleer rows that belong to the configured project; report the rest."""
    scope = get_scope(cfg)
    kid = scope["kleer_project_id"]
    out = dict(week)
    out["time_events"] = [e for e in week.get("time_events", []) if e.get("project_id") == kid]
    out["expenses"] = [x for x in week.get("expenses", []) if x.get("project_id") == kid]
    n_t = len(week.get("time_events", [])) - len(out["time_events"])
    n_e = len(week.get("expenses", [])) - len(out["expenses"])
    for e in week.get("time_events", []):
        if e.get("project_id") != kid:
            plan.ignored.append(f"{e['date']} time kleer:{e['id']} ({e['hours']} h, "
                                f"project {e.get('project_id')})")
    for x in week.get("expenses", []):
        if x.get("project_id") != kid:
            plan.ignored.append(f"{x['date']} expense kleer:{x['id']} ({x.get('description', '')!r}, "
                                f"project {x.get('project_id')})")
    return out


def pick_time_mapping(cfg, ev):
    """Activity-specific mapping wins over a default (no kleer_activity_id) one."""
    best = None
    for m in cfg.get("time_map", []):
        if "kleer_activity_id" in m and m["kleer_activity_id"] != ev.get("activity_id"):
            continue
        if best is None or ("kleer_activity_id" in m and "kleer_activity_id" not in best):
            best = m
    return best


def desired_time_rows(cfg, week, plan: Plan):
    uid = cfg["timekeeper_user_id"]
    rows = {}
    for ev in week.get("time_events", []):
        m = pick_time_mapping(cfg, ev)
        key = str(ev["id"])
        if not m or not all(m.get(k) for k in ("tk_activity_id", "tk_timecode_id")):
            plan.errors.append(
                f"Kleer time event {ev['id']} ({ev['date']}, activity {ev.get('activity_id')}) "
                f"has no complete mapping in config.json 'time_map'")
            continue
        h, mi = split_hours(float(ev["hours"]))
        # Kleer's external comment is the source of truth; config comment is only a fallback.
        text = (ev.get("comment") or "").strip() or m.get("comment", "")
        rows[key] = {
            "userID": uid,
            "date": ev["date"],
            "hours": h,
            "minutes": mi,
            "startTime": None,
            "endTime": None,
            "activityID": m["tk_activity_id"],
            "timeCodeID": m["tk_timecode_id"],
            "projectID": cfg["scope"]["tk_project_id"],
            "comment": with_marker(text, "t", ev["id"]),
            "isInvoiced": False,
        }
    return rows


def desired_expense_rows(cfg, week, plan: Plan):
    uid = cfg["timekeeper_user_id"]
    emap = cfg.get("expense_map", {})
    rows = {}
    for ex in week.get("expenses", []):
        m = emap.get(ex.get("expense_type")) or emap.get("default")
        key = str(ex["id"])
        if not m or not m.get("tk_wagecode_id"):
            plan.errors.append(
                f"Kleer expense entry {ex['id']} ({ex['date']}, type {ex.get('expense_type')!r}) "
                f"has no complete mapping in config.json 'expense_map'")
            continue
        rows[key] = {
            "userID": uid,
            "date": ex["date"],
            "wagecodeID": m["tk_wagecode_id"],
            "projectID": cfg["scope"]["tk_project_id"],
            "quantity": 1,
            "price": round(ex["amount_ore"] / 100, 2),
            "comment": with_marker(ex.get("description", ""), "e", ex["id"]),
        }
    return rows


def _same_time(existing: dict, want: dict) -> bool:
    return (
        str(g(existing, "date", default=""))[:10] == want["date"]
        and int(g(existing, "hours", default=0) or 0) == want["hours"]
        and int(g(existing, "minutes", default=0) or 0) == want["minutes"]
        and g(existing, "projectID") == want["projectID"]
        and g(existing, "activityID") == want["activityID"]
        and g(existing, "timeCodeID") == want["timeCodeID"]
        and (g(existing, "comment", default="") or "").strip() == want["comment"]
    )


def _same_expense(existing: dict, want: dict) -> bool:
    return (
        str(g(existing, "date", default=""))[:10] == want["date"]
        and g(existing, "projectID") == want["projectID"]
        and g(existing, "wagecodeID") == want["wagecodeID"]
        and abs(float(g(existing, "price", default=0) or 0) - want["price"]) < 0.005
        and float(g(existing, "quantity", default=1) or 1) == want["quantity"]
        and (g(existing, "comment", default="") or "").strip() == want["comment"]
    )


def diff(kind, want_rows, existing_rows, same_fn, delete_stale, plan: Plan):
    tag = "t" if kind == "time" else "e"
    by_marker = {}
    unmarked = []
    for r in existing_rows:
        mk = find_marker(g(r, "comment"))
        if mk and mk[0] == tag:
            by_marker[mk[1]] = r
        else:
            unmarked.append(r)

    for key, want in want_rows.items():
        have = by_marker.get(key)
        label = f"{want['date']} {kind} kleer:{key}"
        if have is None:
            plan.add("create", kind, key, label, payload=want)
            for u in unmarked:  # possible manual double entry
                if (str(g(u, "date", default=""))[:10] == want["date"]
                        and g(u, "projectID") == want["projectID"]):
                    plan.add("warn", kind, key,
                             f"{want['date']}: TimeKeeper already has an un-synced {kind} row "
                             f"(id {g(u, 'id')}) on the same project/day - check for a double entry")
                    break
        elif same_fn(have, want):
            plan.add("skip", kind, key, label + " (unchanged)", tk_id=g(have, "id"))
        else:
            body = dict(want, id=g(have, "id"))
            plan.add("update", kind, key, label, payload=body, tk_id=g(have, "id"))

    for key, have in by_marker.items():
        if key not in want_rows:
            op = "delete" if delete_stale else "warn"
            msg = (f"{str(g(have, 'date', default=''))[:10]} {kind} kleer:{key} "
                   f"exists in TimeKeeper but not in Kleer (id {g(have, 'id')})"
                   + ("" if delete_stale else " - kept; set delete_stale=true to remove"))
            plan.add(op, kind, key, msg, tk_id=g(have, "id"))


def split_by_month(week) -> list[dict]:
    """Split a week file into one sub-week per calendar month it touches.

    A week that runs 28 Sep - 4 Oct becomes [28-30 Sep] and [1-4 Oct], each planned,
    applied and read back from TimeKeeper on its own, so a closed/locked month
    (or a failure in one month) can never block or corrupt the other.
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


def build_plan(cfg, week, tk: TimeKeeper, allow_missing_receipts: bool = False) -> Plan:
    plan = Plan()
    uid = cfg["timekeeper_user_id"]
    get_scope(cfg)                        # config sanity first
    check_approval(week, plan, cfg)       # whole week must be approved in Kleer first
    if plan.errors:                       # not approved: stop here, do not even read TimeKeeper
        plan.uid, plan.d_from, plan.d_to = uid, week["from"], week["to"]
        return plan
    week = apply_scope(cfg, week, plan)   # drop everything outside the configured Kleer project
    d_from, d_to = week["from"], week["to"]
    delete_stale = bool(cfg.get("delete_stale", False))

    want_t = desired_time_rows(cfg, week, plan)
    want_e = desired_expense_rows(cfg, week, plan)
    # Never delete based on an incomplete mapping: if anything failed to map,
    # a "stale" row might just be an unmapped one.
    if plan.errors:
        delete_stale = False

    plan.uid, plan.d_from, plan.d_to = uid, d_from, d_to
    diff("time", want_t, tk.time_regs(uid, d_from, d_to), _same_time, delete_stale, plan)
    existing_exp = tk.expense_regs(uid, d_from, d_to)
    diff("expense", want_e, existing_exp, _same_expense, delete_stale, plan)
    plan_receipts(week, want_e, existing_exp, tk, plan, allow_missing_receipts)
    return plan


def _icloud_hint(path: str) -> str:
    """iCloud keeps not-yet-downloaded files as hidden '.<name>.icloud' placeholders."""
    d, n = os.path.split(path)
    if os.path.exists(os.path.join(d, f".{n}.icloud")):
        return (" (it is in iCloud but not downloaded to this Mac - open the folder in Finder "
                "and click the cloud icon, or run `brctl download <path>`)")
    return ""


def plan_receipts(week, want_e, existing_exp, tk, plan: Plan, allow_missing: bool):
    """Every Kleer expense entry with a receipt needs a local file to attach in TimeKeeper."""
    ids = {}
    for r in existing_exp:
        mk = find_marker(g(r, "comment"))
        if mk and mk[0] == "e":
            ids[mk[1]] = g(r, "id")
    for ex in week.get("expenses", []):
        key = str(ex["id"])
        if key not in want_e or not ex.get("has_receipt"):
            continue
        label = f"{ex['date']} expense kleer:{key} receipt"
        path = ex.get("receipt_file")
        if not path:
            msg = (f"{ex['date']} expense kleer:{key} ({ex.get('description', '')!r}, "
                   f"{ex['amount_ore'] / 100:.2f}) has a receipt in Kleer but no receipt_file "
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
        name = os.path.basename(path).lower()
        eid = ids.get(key)
        if eid is not None:
            have = [str(g(f, "fileName", "name", "filename", default="")).lower()
                    for f in tk.expense_files(eid)]
            if name in have:
                plan.add("skip", "expense", key, label + f" ({os.path.basename(path)} already attached)",
                         tk_id=eid)
                continue
        plan.add("receipt", "expense", key, label + f" <- {os.path.basename(path)}",
                 payload={"path": path}, tk_id=eid)


def execute(plan: Plan, tk: TimeKeeper):
    ids = None  # marker -> TimeKeeper expense id, loaded lazily after creates
    for a in plan.actions:
        if a.op == "create":
            (tk.create_time if a.kind == "time" else tk.create_exp)(a.payload)
        elif a.op == "update":
            (tk.update_time if a.kind == "time" else tk.update_exp)(a.payload)
        elif a.op == "delete":
            (tk.delete_time if a.kind == "time" else tk.delete_exp)(a.tk_id)
        elif a.op == "receipt":
            eid = a.tk_id
            if eid is None:
                if ids is None:
                    ids = {}
                    for r in tk.expense_regs(plan.uid, plan.d_from, plan.d_to):
                        mk = find_marker(g(r, "comment"))
                        if mk and mk[0] == "e":
                            ids[mk[1]] = g(r, "id")
                eid = ids.get(a.key)
            if eid is None:
                raise SystemExit(f"Cannot attach receipt: expense kleer:{a.key} not found in "
                                 f"TimeKeeper after creating it.")
            tk.upload_expense_file(eid, a.payload["path"])
        else:
            continue
        time.sleep(0.2)  # be gentle with rate limits


def count_ops(plan: Plan) -> dict:
    return {op: sum(1 for a in plan.actions if a.op == op)
            for op in ("create", "update", "delete", "receipt", "skip", "warn")}


def print_plan(plan: Plan, applied: bool, summary: bool = True):
    verb = {"create": "CREATE", "update": "UPDATE", "delete": "DELETE",
            "receipt": "ATTACH", "skip": "ok    ", "warn": "WARN  "}
    for a in plan.actions:
        print(f"  {verb[a.op]}  {a.detail}")
    for e in plan.errors:
        print(f"  ERROR   {e}")
    if plan.ignored:
        print(f"\n  Not replicated ({len(plan.ignored)} items outside the configured Kleer project):")
        for i in plan.ignored:
            print(f"    - {i}")
    if summary:
        print_summary([plan], applied)


def print_summary(plans, applied: bool):
    c = {op: sum(count_ops(p)[op] for p in plans) for op in count_ops(Plan())}
    n_err = sum(len(p.errors) for p in plans)
    t = "applied" if applied else "dry run - nothing written"
    print(f"\n{t}: {c['create']} create, {c['update']} update, "
          f"{c['delete']} delete, {c['receipt']} receipts, {c['skip']} unchanged, "
          f"{c['warn']} warnings, {n_err} errors")


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------
def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def make_client() -> TimeKeeper:
    user, pw = os.environ.get("TK_USER"), os.environ.get("TK_PASSWORD")
    if not user or not pw:
        raise SystemExit("Set TK_USER and TK_PASSWORD in your environment first.")
    return TimeKeeper(user, pw, os.environ.get("TK_BASE", "https://api2.timekeeper.se"))


def cmd_discover(args):
    tk = make_client()
    cfg = load_json(args.config) if os.path.exists(args.config) else {}
    uid = cfg.get("timekeeper_user_id")
    print("== /Login/me ==")
    print(json.dumps(tk._call("GET", "/api/v1/Login/me"), indent=2, ensure_ascii=False))
    params = {"UserID": uid} if uid else {}
    print("\n== Projects (ongoing) ==  [tk_project_id]")
    for p in tk.paged("/api/v1/Project", dict(params, Status=0)):
        print(f"  {g(p, 'id')}\t{g(p, 'projectNr', default='')}\t{g(p, 'name', default='')}")
    print("\n== Activities ==  [tk_activity_id]")
    for a in tk.paged("/api/v1/Activity", dict(params, IsActive="true")):
        print(f"  {g(a, 'id')}\t{g(a, 'name', default='')}")
    print("\n== Time codes ==  [tk_timecode_id]")
    for t in tk.paged("/api/v1/TimeCode", dict(params, IsActive="true")):
        print(f"  {g(t, 'id')}\t{g(t, 'name', default='')}\t(activity {g(t, 'activityID', default='-')})")
    print("\nExpense wage codes are not exposed as a list endpoint; take wagecodeID from an"
          " existing expense row (GET /api/v1/ExpenseRegistration) or ask your TimeKeeper administrator.")


def validate_week(week) -> list[str]:
    """Check that a week file has the documented shape (see schema/week.schema.json).

    Meant to catch mistakes made by whichever agent produced the file, before any
    TimeKeeper call. Returns a list of problems (empty = valid).
    """
    errs: list[str] = []

    def is_date(v):
        try:
            datetime.date.fromisoformat(str(v))
            return len(str(v)) == 10
        except ValueError:
            return False

    if not isinstance(week, dict):
        return ["week file must be a JSON object"]
    for k in ("from", "to"):
        if not is_date(week.get(k)):
            errs.append(f"'{k}' must be a date like 2026-10-05")
    if is_date(week.get("from")) and is_date(week.get("to")) and week["from"] > week["to"]:
        errs.append("'from' is after 'to'")
    for k in ("time_events", "expenses"):
        if not isinstance(week.get(k), list):
            errs.append(f"'{k}' must be a list (use [] when empty)")
    rng = (week.get("from"), week.get("to"))

    def in_range(d):
        return not (is_date(rng[0]) and is_date(rng[1])) or rng[0] <= d <= rng[1]

    seen = set()
    for i, e in enumerate(week.get("time_events") or []):
        w = f"time_events[{i}]"
        if not isinstance(e, dict):
            errs.append(f"{w} must be an object"); continue
        if e.get("id") in (None, ""):
            errs.append(f"{w}: 'id' is required")
        elif e["id"] in seen:
            errs.append(f"{w}: duplicate id {e['id']}")
        seen.add(e.get("id"))
        if not is_date(e.get("date")):
            errs.append(f"{w}: 'date' must be yyyy-mm-dd")
        elif not in_range(e["date"]):
            errs.append(f"{w}: date {e['date']} is outside from/to")
        h = e.get("hours")
        if isinstance(h, bool) or not isinstance(h, (int, float)) or not 0 < h <= 24:
            errs.append(f"{w}: 'hours' must be a number between 0 and 24 (decimal hours, e.g. 7.5)")
        if not isinstance(e.get("activity_id"), int):
            errs.append(f"{w}: 'activity_id' must be an integer")
        if "project_id" not in e or not (e["project_id"] is None or isinstance(e["project_id"], int)):
            errs.append(f"{w}: 'project_id' must be an integer or null")
        if not isinstance(e.get("status"), str) or not e["status"]:
            errs.append(f"{w}: 'status' is required (copy the source system's approval status)")
        if "comment" in e and not isinstance(e["comment"], str):
            errs.append(f"{w}: 'comment' must be a string")
    seen = set()
    for i, x in enumerate(week.get("expenses") or []):
        w = f"expenses[{i}]"
        if not isinstance(x, dict):
            errs.append(f"{w} must be an object"); continue
        if x.get("id") in (None, ""):
            errs.append(f"{w}: 'id' is required")
        elif x["id"] in seen:
            errs.append(f"{w}: duplicate id {x['id']}")
        seen.add(x.get("id"))
        if not is_date(x.get("date")):
            errs.append(f"{w}: 'date' must be yyyy-mm-dd")
        elif not in_range(x["date"]):
            errs.append(f"{w}: date {x['date']} is outside from/to")
        a = x.get("amount_ore")
        if isinstance(a, bool) or not isinstance(a, int) or a < 0:
            errs.append(f"{w}: 'amount_ore' must be a non-negative integer (amount incl. VAT in 1/100 currency units)")
        if "project_id" not in x or not (x["project_id"] is None or isinstance(x["project_id"], int)):
            errs.append(f"{w}: 'project_id' must be an integer or null")
        if not isinstance(x.get("has_receipt", False), bool):
            errs.append(f"{w}: 'has_receipt' must be true or false")
    return errs


def cmd_validate(args):
    week = load_json(args.week)
    errs = validate_week(week)
    if errs:
        print(f"{args.week}: {len(errs)} problem(s)")
        for e in errs:
            print(f"  ERROR   {e}")
        raise SystemExit(1)
    print(f"{args.week}: valid ({len(week['time_events'])} time events, {len(week['expenses'])} expenses)")


def cmd_sync(args, apply: bool):
    cfg, week = load_json(args.config), load_json(args.week)
    if not cfg.get("timekeeper_user_id"):
        raise SystemExit("config.json: timekeeper_user_id is required (see `discover`).")
    problems = validate_week(week)
    if problems:
        for p in problems:
            print(f"  ERROR   {p}")
        raise SystemExit(f"\n{args.week} is not a valid week file (see schema/week.schema.json). "
                         f"Nothing was written.")
    print(f"Week {week.get('week', '?')}  {week['from']} .. {week['to']}\n")

    # The whole week must be approved in Kleer before ANY month part is touched.
    gate = Plan()
    check_approval(week, gate, cfg)
    if gate.errors:
        print_plan(gate, applied=False)
        if apply:
            raise SystemExit("\nNothing was written: the week is not approved in Kleer.")
        return

    tk = make_client()
    segs = split_by_month(week)
    plans = []
    for seg in segs:
        plan = build_plan(cfg, seg, tk, allow_missing_receipts=args.allow_missing_receipts)
        plans.append(plan)
        if not apply:   # when applying, the blocks are printed after execution below
            if len(segs) > 1:
                print(f"--- Month {seg['month']}: {seg['from']} .. {seg['to']} "
                      f"(handled separately) ---")
            print_plan(plan, applied=False, summary=False)

    if apply and any(p.errors for p in plans):
        for seg, p in zip(segs, plans):
            print(f"--- Month {seg['month']} ---")
            print_plan(p, applied=False, summary=False)
        raise SystemExit("\nRefusing to apply while there are mapping errors. Fix config.json first.")

    failed = []
    if apply:
        for seg, plan in zip(segs, plans):
            if len(segs) > 1:
                print(f"--- Month {seg['month']}: {seg['from']} .. {seg['to']} ---")
            try:
                execute(plan, tk)
                print_plan(plan, applied=True, summary=False)
            except (SystemExit, Exception) as e:   # one month failing must not block the other
                failed.append(seg["month"])
                print(f"  FAILED  month {seg['month']}: {e}")
    print_summary(plans, applied=apply)
    if failed:
        raise SystemExit(f"\nMonth(s) not fully posted: {', '.join(failed)}. The other month(s) "
                         f"were still processed. Fix the problem and run the same week again; "
                         f"already-posted days are updated, never duplicated.")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default="config.json")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("discover")
    pv = sub.add_parser("validate", help="check a week file's structure, no network access")
    pv.add_argument("--week", required=True)
    for name in ("plan", "apply"):
        p = sub.add_parser(name)
        p.add_argument("--week", required=True, help="week JSON produced from Kleer")
        p.add_argument("--allow-missing-receipts", action="store_true",
                       help="warn instead of failing when a Kleer receipt has no local file")
    args = ap.parse_args(argv)
    if args.cmd == "discover":
        cmd_discover(args)
    elif args.cmd == "validate":
        cmd_validate(args)
    else:
        cmd_sync(args, apply=(args.cmd == "apply"))


if __name__ == "__main__":
    main()
