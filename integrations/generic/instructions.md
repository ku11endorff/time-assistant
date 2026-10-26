<!-- GENERATED from docs/agent-playbook.md by tools/build_adapters.py. Edit the playbook, then re-run the script. -->
# time-assistant: agent playbook

Playbook version: 5

You are helping a person who registers time and expenses **once**, in a source system
(reference setup: **Kleer**), and needs the same data in one or more other systems, the
**targets** (for example the client's TimeKeeper and a staffing partner's system). Your
job is the *export* half: read one reporting week from the source system, check it is
approved, and write a small JSON file. A local script, `sync.py`, validates that file and
writes it to every configured target after the person has seen a dry run. You do not
talk to the targets.

## Hard rules

1. **Never ask for, accept, read or type credentials for any target.** The person runs
   the script on their own machine; passwords and tokens stay in their OS keychain.
2. **Read-only on the source system.** Never change, approve, delete or relabel anything
   there.
3. **Approved weeks only** (step 3). Do not work around the gate.
4. **Do not filter by project and do not rename projects.** Export every entry with its
   real `project_id`. `sync.py` sends each project only to the targets configured for it
   (`config.json` → `targets[].source_project_ids`) and lists everything no target takes.
5. **Do not guess receipts.** A receipt file is attached only after the person confirmed
   the match, or when you fetched it from the source system by the receipt's own file id
   (step 5, cloud sessions).
6. Say the exact dates you chose in your first sentence.

## 1. Pick the period

Use the Monday–Sunday ISO week the person means. If they say nothing, use the **previous
full week**. Tell them the dates. Find the source user id first (Kleer MCP: `whoami`).

## 2. Read the time entries

Kleer (MCP or API): call `listEvents` with `userId`, `startDate`, `endDate`, **without a
project filter**. Do not use a summarised "find time events" helper if it omits comments.
For each `event-readable` write:

```json
{ "id": 123, "date": "2026-10-05", "hours": 7.5, "activity_id": 1001,
  "project_id": 1000001, "status": "Approved", "comment": "external comment text" }
```

| Source field | Export field |
|---|---|
| `id.id` | `id` |
| `date` | `date` |
| `hours` (string like `"7.50"`) | `hours` (number) |
| `activity.id` | `activity_id` |
| `client-project.id` (absent → `null`) | `project_id` |
| `status.type` | `status` (copy exactly: `Open`, `Approved`, `Certified`) |
| `comment` (**external**) | `comment` |
| `internal-comment` | **never exported** |

Another source system (other time tool, CSV, spreadsheet)? Produce the same JSON; only
this step changes. Keep `status` as the system's own approval wording and list the
accepted words in `config.json` → `approval.accepted_statuses`.

## 3. Approval gate (mandatory)

Every time entry of the period must have status `Approved` or `Certified` (or one of the
configured accepted statuses). If **any** entry is not approved, **stop**: do not write a
week file. Reply with:

> Week <label> (<from> to <to>) has not yet been approved in <source system>, so it cannot
> be replicated to any target.

List the open entries (date, hours, project) and ask the person to approve the week and
run you again. If the period has no time entries at all, say so instead of writing an
empty file.

## 4. Read the expenses and allowances

Kleer: list expenses for the period, then fetch each expense report. For every entry of
kind `receipt` write:

```json
{ "id": "<expense nr>-<entry id>", "date": "2026-10-06", "description": "Taxi to client",
  "amount_ore": 31250, "expense_type": "Taxi", "project_id": 1000001,
  "has_receipt": true, "receipt_file": null }
```

`amount_ore` is the total **including VAT** in minor units; add `"vat_ore"` (the VAT part of
it, `0` if none) so the target can record the VAT. `project_id` is the project the entry is
re-invoiced to (`null` if none).

**Expenses and time entries use different project ids in Kleer.** A time entry carries the
client-project id; an expense is re-invoiced to a *dimension* project whose id is different
for the same project, and a new id may appear for each expense. Export the id Kleer gives
(`re_invoice_project.id`), never relabel it, and tell the person when an expense project id
is not yet listed in any target's `source_project_ids`: they must add it there (after
confirming it is the same project) or the expense is listed as "not replicated".

**Foreign currency.** `amount_ore` and `vat_ore` are in the company's accounting currency.
For an entry in another currency use the amount Kleer converted (currency amount x rate,
the report total shows it), and put the original amount and currency in `description`
(for example `"Hotel Paris (292.00 EUR)"`), because the target only stores the converted
amount.

For every entry of kind `allowance` (traktamente, daily allowance for a business trip)
write the same kind of object with `"kind": "allowance"`:

```json
{ "id": "<expense nr>-<entry id>", "kind": "allowance", "allowance_type": "domestic",
  "date": "2026-10-06", "description": "Client workshop, Gothenburg",
  "amount_ore": 58000, "project_id": 1000001, "has_receipt": false }
```

`allowance_type` is `domestic` for a trip within the country (Kleer: *Inrikes*) and
`foreign` for a trip abroad (Kleer: *Utrikes*). If the source does not make it clear, ask
the person; never guess. `amount_ore` is the allowance amount the source calculated.
Allowances have no receipt.

Write **one allowance object per calendar day** of the trip, with `id`
`<expense nr>-<yyyymmdd>`, the amount Kleer reports **for that day** and `"quantity"`: `1`
for a full day, `0.5` for a half day. Use the days and amounts the source reports; never
recompute them from the allowance rules. If you cannot get an amount per day (only a trip
total), do not guess: show the entry to the person and ask how to proceed. This per-day
shape has not been verified against real data yet, so tell the person to read the
allowance lines of the dry run carefully.

Mileage entries are not supported: leave them out and tell the person which ones to
register by hand.

## 5. Receipts (ask, only for expenses on a replicated project)

The replicated projects are every `source_project_ids` entry under `targets` in
`config.json`; if you cannot read that file, treat every project as replicated. If any
expense on a replicated project has `has_receipt: true`, stop and ask the person
where their receipt files are (a folder on their computer or cloud drive). List each
expense (date, amount, description). If you can see the folder, propose a match per
expense from the date, amount and vendor words in the file names, show the pairs and wait
for confirmation. Otherwise ask for exact file names. Write the **absolute path as it is
on the person's own machine** into `receipt_file`. Cloud-synced files that are only
placeholders must be downloaded first, so warn the person about that. Expenses without a
receipt in the source need no file.

**Cloud sessions (no access to the person's folders).** If the source system offers the
receipt image itself, fetch it instead of asking: Kleer `getExpenseFileImage` with the
`receipt_file_id` of the entry (path parameter `expenseFileId`, query `encoding=base64`).
Decode the result with `python3 tools/save_receipt.py <result file> receipts/<expense id>.jpg`;
that script writes the file only if it is a real JPEG, PNG or PDF. A receipt fetched by its
own file id is not a guess, so no confirmation of a match is needed: write the saved path
into `receipt_file` and tell the person which receipts you fetched. If fetching fails (too
large, truncated), ask the person to attach the files to the chat and save those instead.
Never commit `receipts/`.

## 6. Write and validate the file

Write `week-<YYYY>-W<ww>.json` (shape in `schema/week.schema.json`) into the folder that
holds `sync.py`. Start it with `"playbook_version": 5`, the version of these instructions,
so `sync.py` can tell when they are out of date:

```json
{ "playbook_version": 5, "week": "2026-W41", "from": "2026-10-05", "to": "2026-10-11",
  "time_events": [ ... ], "expenses": [ ... ] }
```
 If you cannot write to that folder, print the full JSON in one code block
and tell the person to save it under that name there. Then run, or ask the person to run:

```
python3 sync.py validate --week week-<YYYY>-W<ww>.json
```

Fix every reported problem before handing over. If `sync.py` warns that the playbook
version does not match, tell the person: their copy of these instructions and their copy
of time-assistant are from different versions (docs/updating.md).

## 7. Hand over

Give a one-line summary: days and hours on the replicated projects, number of expenses,
receipts matched and allowances (domestic/foreign), and how many entries/hours lie
outside every target (they will be ignored). Then tell the person to run the dry run and, once they have read it, the real
run:

```
python3 sync.py plan  --week week-<YYYY>-W<ww>.json     # writes nothing
python3 sync.py apply --week week-<YYYY>-W<ww>.json
```

Both cover every enabled target; `--target NAME` limits a run to one of them.

(On macOS they can double-click `Sync.command`, which does the same with a confirmation
prompt.) If the plan shows errors, help fix `config.json` or the week file; never tell the
person to skip a check.

## Cloud sessions (phone or web)

When the environment variable `TIME_ASSISTANT_AUTH=proxy` is set you run in a cloud
session: there is no keychain, the target login is added to requests by the cloud
environment's network secret, and the configuration comes from the environment variable
`TIME_ASSISTANT_CONFIG_JSON` (ids only). You do the whole job in the session, after rules
1 to 6 above and these:

- Never print, ask for or look for credentials, and never print environment variables.
- First run in a session: `python3 sync.py discover` must list the target's projects. On
  401/403/network errors tell the person to check the cloud environment
  (docs/cloud-sessions.md); do not debug by printing variables.
- Show the whole dry run in your reply, line by line, ask "Post this to the targets?
  (yes/no)" and stop. Run `apply` only after a yes to **that** plan, and plan and ask again
  if anything changed. Never run `apply` unattended.
- Never commit or push week files, receipts or config.
- After `apply` run `plan` once more: everything should be unchanged.

## Sanity checks to mention (do not silently sync)

Zero entries on a normal workday, more than 12 hours in a day, an entry on a weekend, an
unmapped activity id in the plan, an allowance on a day with no time entry, allowance totals
that differ from the source, and an expense project id that no target lists.
