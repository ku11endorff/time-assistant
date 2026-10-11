"""TimeKeeper (api2.timekeeper.se) as a target. Setup and field mapping:
docs/targets/timekeeper.md."""
from __future__ import annotations

import base64
import json
import mimetypes
import os
import time
import urllib.error
import urllib.parse
import urllib.request

from .. import markers
from .base import Existing, Target, Wanted

DEFAULT_BASE = "https://api2.timekeeper.se"


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


class TimeKeeperAPI:
    """Minimal TimeKeeper REST client, standard library only."""

    def __init__(self, user: str, password: str, base: str = DEFAULT_BASE):
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
                raise SystemExit(f"Cannot reach TimeKeeper ({e.reason}). Check the network "
                                 f"and settings.base_url.")

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
        boundary = "----timeassistant" + str(int(time.time() * 1000))
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


class TimeKeeperTarget(Target):
    type = "timekeeper"
    display_name = "TimeKeeper"
    supports_expenses = True
    supports_receipts = True
    split_by_month = True
    needs_username = True
    secrets = ("password",)
    required_settings = ("user_id", "project_id")
    time_map_fields = ("activity_id", "timecode_id")
    expense_map_fields = ("wagecode_id",)
    write_pause = 0.2

    def __init__(self, config: dict, secrets: dict | None = None, api=None):
        super().__init__(config, secrets)
        # Tolerant on purpose: `discover` runs before user_id/project_id are known.
        self.user_id = self.settings.get("user_id")
        self.project_id = self.settings.get("project_id")
        self.api = api or TimeKeeperAPI(config.get("username", ""), (secrets or {}).get("password", ""),
                                        self.settings.get("base_url") or DEFAULT_BASE)

    @classmethod
    def check_settings(cls, config):
        s = config.get("settings") or {}
        problems = []
        for k in ("user_id", "project_id"):
            if k in s and (isinstance(s[k], bool) or not isinstance(s[k], int)):
                problems.append(f"settings.{k} must be a number (run `discover` to find it)")
        if s.get("base_url") and not str(s["base_url"]).startswith("https://"):
            problems.append("settings.base_url must start with https://")
        return problems

    @classmethod
    def identity(cls, config):
        s = config.get("settings") or {}
        return ((s.get("base_url") or DEFAULT_BASE).rstrip("/"), s.get("user_id"), s.get("project_id"))

    # ---- reading ------------------------------------------------------------------------
    def existing(self, kind, d_from, d_to):
        rows = (self.api.time_regs if kind == "time" else self.api.expense_regs)(
            self.user_id, d_from, d_to)
        out = []
        for r in rows:
            if g(r, "projectID") != self.project_id:   # another project: not this target's rows
                continue
            out.append(Existing(id=g(r, "id"), key=markers.find(g(r, "comment"), kind),
                                date=str(g(r, "date", default=""))[:10],
                                project=g(r, "projectID"), raw=r))
        return out

    # ---- mapping ------------------------------------------------------------------------
    def build(self, kind, item, mapping):
        if kind == "time":
            h, mi = split_hours(float(item["hours"]))
            payload = {
                "userID": self.user_id,
                "date": item["date"],
                "hours": h,
                "minutes": mi,
                "startTime": None,
                "endTime": None,
                "activityID": mapping["activity_id"],
                "timeCodeID": mapping["timecode_id"],
                "projectID": self.project_id,
                "comment": self.comment(kind, item, mapping),
                "isInvoiced": False,
            }
        else:
            payload = {
                "userID": self.user_id,
                "date": item["date"],
                "wagecodeID": mapping["wagecode_id"],
                "projectID": self.project_id,
                "quantity": 1,
                "price": round(item["amount_ore"] / 100, 2),
                "comment": self.comment(kind, item, mapping),
            }
        return Wanted(payload=payload, project=self.project_id)

    def same(self, kind, existing, wanted):
        have, want = existing.raw, wanted.payload
        common = (
            str(g(have, "date", default=""))[:10] == want["date"]
            and g(have, "projectID") == want["projectID"]
            and markers.normalise(g(have, "comment", default="")) == markers.normalise(want["comment"])
        )
        if kind == "time":
            return (common
                    and int(g(have, "hours", default=0) or 0) == want["hours"]
                    and int(g(have, "minutes", default=0) or 0) == want["minutes"]
                    and g(have, "activityID") == want["activityID"]
                    and g(have, "timeCodeID") == want["timeCodeID"])
        return (common
                and g(have, "wagecodeID") == want["wagecodeID"]
                and abs(float(g(have, "price", default=0) or 0) - want["price"]) < 0.005
                and float(g(have, "quantity", default=1) or 1) == want["quantity"])

    # ---- writing ------------------------------------------------------------------------
    def create(self, kind, wanted):
        (self.api.create_time if kind == "time" else self.api.create_exp)(wanted.payload)

    def update(self, kind, existing, wanted):
        (self.api.update_time if kind == "time" else self.api.update_exp)(
            dict(wanted.payload, id=existing.id))

    def delete(self, kind, existing):
        (self.api.delete_time if kind == "time" else self.api.delete_exp)(existing.id)

    def attached_files(self, expense):
        return [str(g(f, "fileName", "name", "filename", default=""))
                for f in self.api.expense_files(expense.id)]

    def attach_receipt(self, expense, path):
        self.api.upload_expense_file(expense.id, path)

    # ---- setup help -----------------------------------------------------------------------
    def discover(self):
        uid = self.user_id
        print("== /Login/me ==  [settings.user_id is the id below]")
        print(json.dumps(self.api._call("GET", "/api/v1/Login/me"), indent=2, ensure_ascii=False))
        params = {"UserID": uid} if uid else {}
        print("\n== Projects (ongoing) ==  [settings.project_id: use the first column, not the project number]")
        for p in self.api.paged("/api/v1/Project", dict(params, Status=0)):
            print(f"  {g(p, 'id')}\t{g(p, 'projectNr', default='')}\t{g(p, 'name', default='')}")
        print("\n== Activities ==  [time_map: activity_id]")
        for a in self.api.paged("/api/v1/Activity", dict(params, IsActive="true")):
            print(f"  {g(a, 'id')}\t{g(a, 'name', default='')}")
        print("\n== Time codes ==  [time_map: timecode_id]")
        for t in self.api.paged("/api/v1/TimeCode", dict(params, IsActive="true")):
            print(f"  {g(t, 'id')}\t{g(t, 'name', default='')}\t(activity {g(t, 'activityID', default='-')})")
        print("\nExpense wage codes (expense_map: wagecode_id) have no list endpoint; take wagecodeID "
              "from an existing expense row (GET /api/v1/ExpenseRegistration) or ask your "
              "TimeKeeper administrator.")
