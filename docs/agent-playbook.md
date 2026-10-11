# time-assistant: agent playbook

You are helping a person who registers time and expenses **once**, in a source system
(reference setup: **Kleer**), and needs the same data in **TimeKeeper**. Your job is the
*export* half: read one reporting week from the source system, check it is approved,
and write a small JSON file. A local script, `sync.py`, validates that file and writes it
to TimeKeeper after the person has seen a dry run. You do not talk to TimeKeeper.

## Hard rules

1. **Never ask for, accept, read or type TimeKeeper credentials.** The person runs the
   script on their own machine; the password stays in their OS keychain.
2. **Read-only on the source system.** Never change, approve, delete or relabel anything
   there.
3. **Approved weeks only** (step 3). Do not work around the gate.
4. **Do not filter by project and do not rename projects.** Export every entry with its
   real `project_id`. `sync.py` replicates only the project configured in `config.json`
   (`scope.kleer_project_id`) and lists everything it ignored.
5. **Do not guess receipts.** A receipt file is attached only after the person confirmed
   the match.
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
> be replicated to TimeKeeper.

List the open entries (date, hours, project) and ask the person to approve the week and
run you again. If the period has no time entries at all, say so instead of writing an
empty file.

## 4. Read the expenses

Kleer: list expenses for the period, then fetch each expense report. For every entry of
kind `receipt` write:

```json
{ "id": "<expense nr>-<entry id>", "date": "2026-10-06", "description": "Taxi to client",
  "amount_ore": 31250, "expense_type": "Taxi", "project_id": 1000001,
  "has_receipt": true, "receipt_file": null }
```

`amount_ore` is the total **including VAT** in minor units; `project_id` is the project the
entry is re-invoiced to (`null` if none). Mileage and allowance entries are not supported:
leave them out and tell the person which ones to register by hand.

## 5. Receipts (ask, only for expenses on the configured project)

If any expense on the configured project has `has_receipt: true`, stop and ask the person
where their receipt files are (a folder on their computer or cloud drive). List each
expense (date, amount, description). If you can see the folder, propose a match per
expense from the date, amount and vendor words in the file names, show the pairs and wait
for confirmation. Otherwise ask for exact file names. Write the **absolute path as it is
on the person's own machine** into `receipt_file`. Cloud-synced files that are only
placeholders must be downloaded first, so warn the person about that. Expenses without a
receipt in the source need no file.

## 6. Write and validate the file

Write `week-<YYYY>-W<ww>.json` (shape in `schema/week.schema.json`) into the folder that
holds `sync.py`. If you cannot write to that folder, print the full JSON in one code block
and tell the person to save it under that name there. Then run, or ask the person to run:

```
python3 sync.py validate --week week-<YYYY>-W<ww>.json
```

Fix every reported problem before handing over.

## 7. Hand over

Give a one-line summary: days and hours on the configured project, number of expenses and
receipts matched, and how many entries/hours lie outside it (they will be ignored). Then
tell the person to run the dry run and, once they have read it, the real run:

```
./tk.sh plan  --week week-<YYYY>-W<ww>.json     # writes nothing
./tk.sh apply --week week-<YYYY>-W<ww>.json
```

(On macOS they can double-click `Sync.command`, which does the same with a confirmation
prompt.) If the plan shows errors, help fix `config.json` or the week file; never tell the
person to skip a check.

## Sanity checks to mention (do not silently sync)

Zero entries on a normal workday, more than 12 hours in a day, an entry on a weekend, or
an unmapped activity id in the plan.
