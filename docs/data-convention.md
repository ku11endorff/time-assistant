# Data convention

The week file is the only thing that crosses from the source side to the target side.
This page covers the source side (how the agent fills the week file), the rules every
target follows to recognise its rows, and, at the end, one
[table of what each piece of data is called in every system](#semantic-data-convention-across-systems).
How each target stores the data in detail is on its own page under [targets/](targets/).

## Source → week file

Reference source system: **Kleer**. Shape: [`schema/week.schema.json`](../schema/week.schema.json);
`python3 sync.py validate --week FILE` checks it offline. Every id below is a made-up example.

### Time entries (`time_events`)

| Source field (Kleer `listEvents`) | Week file | Rule |
|---|---|---|
| `id.id` | `id` | Stable id in the source; letters, digits, `-`, `_` only |
| `date` | `date` | `yyyy-mm-dd`, inside `from`..`to` |
| `hours` (string, e.g. `"7.50"`) | `hours` | Decimal number, e.g. `7.5` |
| `activity.id` | `activity_id` | Mapped per target by `time_map` |
| `client-project.id` (absent → `null`) | `project_id` | Decides which targets get the entry (`source_project_ids`). Never relabelled |
| `status.type` | `status` | Copied exactly (`Open`, `Approved`, `Certified`); used by the approval gate, never sent to a target |
| `comment` (**external**) | `comment` | Sent to targets |
| `internal-comment` | n/a | **Never exported** |

Export **every** entry of the week on every project; `sync.py` does the routing and lists
what no target takes.

### Expenses (`expenses`)

| Source field (Kleer receipt entry) | Week file | Rule |
|---|---|---|
| `<expense nr>-<entry id>` | `id` | e.g. `"5-1"` |
| `date` | `date` | Receipt date |
| `description` | `description` | Sent to targets |
| total incl. VAT | `amount_ore` | Integer, minor units (1/100 of the company's currency). A foreign-currency entry uses the converted amount, and the original amount and currency go in `description` |
| VAT part | `vat_ore` | Optional integer, minor units. Sent to targets that record VAT |
| expense type | `expense_type` | Mapped per target by `expense_map` (type, else `default`) |
| project the entry is re-invoiced to | `project_id` | `null` if none. **In Kleer this is a different id than the client-project id of time entries** (a dimension project, `re_invoice_project.id`), and each expense may get a new one: list every id you have seen in the target's `source_project_ids`. Never relabelled |
| receipt exists | `has_receipt` | `true` → a confirmed local file is needed if a target takes receipts |
| confirmed file | `receipt_file` | Path on the machine that runs `sync.py`: a file the person confirmed, or one fetched from Kleer by its own file id in a cloud session (`tools/save_receipt.py`) |
| entry kind | `kind` | `receipt` (default) or `allowance` |
| mileage entries | n/a | Not supported; left out and named to the person |

### Daily allowances (traktamente)

Kleer allowance entries go into `expenses` too, with `"kind": "allowance"`:

| Source field (Kleer allowance entry) | Week file | Rule |
|---|---|---|
| `<expense nr>-<entry id>` | `id` | Same form as receipts |
| type of trip: *Inrikes* / *Utrikes* | `allowance_type` | `domestic` / `foreign`; picks the target's `allowance_map` entry. Ask the person if unclear |
| `date` | `date` | As the source gives it |
| `description` (purpose) | `description` | Sent to targets |
| calculated allowance | `amount_ore` | The amount the source calculated (tax-free part) **for that day**, minor units |
| full or half day | `quantity` | Optional: `1` (default) full day, `0.5` half day. Write one object per calendar day of the trip, id `<expense nr>-<yyyymmdd>` |
| project it is re-invoiced to | `project_id` | Decides which targets get it |
| | `has_receipt` | Always `false` |

Each target takes allowances only if it has an `allowance_map` entry for the type.

### Another source system

Only the export changes. Make your agent (or a script) write the same week file, keep the
source's own approval wording in `status`, list the accepted words in `config.json` →
`approval.accepted_statuses`, and set `source.name` so messages name your system.

## Rows in targets

| Concept | Convention |
|---|---|
| Row identity | A tag in the row, normally at the end of its comment: `[ta:t:<id>]` for time, `[ta:e:<id>]` for expenses |
| Re-run | Rows found by tag are updated if different and skipped if equal; nothing is duplicated |
| Rows typed by hand (no tag) | Never edited or deleted. WARN if one shares project and day with a new row |
| Entry removed in the source (or moved to another project) | Kept with a WARN, unless the target has `"delete_stale": true` |
| Incomplete mapping | Nothing is deleted while any entry of the target is unmapped |
| Month boundary | For targets with `split_by_month`, each calendar month is a separate batch |
| Older tags | `[kleer:t:<id>]` / `[kleer:e:<id>]` from earlier versions still match and are not rewritten only to change the prefix |

## Semantic data convention across systems

One row per meaning, one column per system: what the same piece of data is called, and
how it is converted, in the week file, in the reference source and in every target. Read a
row across to see how a value travels; read a column to see everything one system needs.

- `—` the system has no such field, or it plays no part in that system.
- *not sent* the system has the field, but time-assistant deliberately does not copy it.
- *not replicated* time-assistant does not carry this kind of data to the target at all.
- `settings.*`, `time_map`, `expense_map`, `allowance_map` refer to that target's entry in
  [config.json](configuration.md).

**Every target has a column here.** A new target adds its column on the right, and fills
every row, in the same pull request that adds the target
([adding-a-target.md](adding-a-target.md#4-the-docs)). A new piece of data adds a row, filled
for every column. `tests/test_registry.py` fails if a built-in target has no column or a
row is missing a cell.

| Meaning | Week file | Kleer (source) | TimeKeeper (target) |
|---|---|---|---|
| **Time entry** | item of `time_events` | event from `listEvents` | `TimeRegistration` |
| Entry id, row identity | `id` | `id.id` | tag `[ta:t:<id>]` at the end of `comment` |
| Person | — (whoever exports the week) | the `userId` the week is read for | `userID` = `settings.user_id` |
| Work date | `date` (`yyyy-mm-dd`) | `date` | `date` |
| Duration | `hours`, decimal (`7.5`) | `hours`, string (`"7.50"`) | `hours` + `minutes` (7 h 30 min) |
| Kind of work | `activity_id` | `activity.id` | `activityID` + `timeCodeID` via `time_map` |
| Project | `project_id`; routes the entry to targets by `source_project_ids` | `client-project.id` | `projectID` = `settings.project_id` |
| Approval | `status`, copied exactly | `status.type`: `Open`, `Approved`, `Certified` | *not sent*; checked before anything is written |
| Customer-visible comment | `comment` | `comment` (external) | `comment`, with the tag appended |
| Internal comment | — (never exported) | `internal-comment` | — |
| Invoicing state | — | `invoiceable`, `invoiced-*` | `isInvoiced`, always `false` |
| Start and end time | — | — | `startTime`, `endTime`, always empty |
| **Expense (receipt)** | item of `expenses`, `kind` `receipt` | expense report entry, kind `receipt` | `ExpenseRegistration` |
| Entry id, row identity | `id` = `<expense nr>-<entry id>` | expense `nr` + entry id | tag `[ta:e:<id>]` at the end of `comment` |
| Date | `date` | `date` | `date` |
| Description | `description` | `description` | `comment`, with the tag appended |
| Amount incl. VAT | `amount_ore`, minor units | `amount_ore` | `price` = `amount_ore` / 100, `quantity` = 1 |
| VAT part | `vat_ore` (optional) | `vat_ore` | `receiptVATAmount` = `vat_ore` / 100, when present |
| Expense type | `expense_type` | expense type | `wagecodeID` via `expense_map` (type, else `default`) |
| Re-invoiced to project | `project_id` | project the entry is re-invoiced to (`re_invoice_project.id`: a dimension-project id, **not** the client-project id of time entries) | `projectID` = `settings.project_id` |
| Receipt category ("Kategori") | — | expense type / category | `receiptCategoryID` = `expense_map.*.receipt_category_id`, when set |
| Paid by ("Betalt av") | — | — (Kleer: paid privately or by company card) | `receiptPaymentType` via `expense_map.*.paid_by`: `self` = 0, `company` = 1, when set |
| Receipt | `has_receipt` + `receipt_file` (confirmed local path, or fetched from Kleer by `receipt_file_id`) | receipt file on the entry (`getExpenseFileImage`) | file uploaded to `/api/v1/File/ExpenseRegistrationFile` |
| **Daily allowance (traktamente)** | item of `expenses`, `kind` `allowance` | expense report entry, kind `allowance` | `ExpenseRegistration`, *Övrigt* |
| Entry id, row identity | `id` = `<expense nr>-<entry id>` | expense `nr` + entry id | tag `[ta:e:<id>]` at the end of `comment` |
| Trip type | `allowance_type`: `domestic` / `foreign` | *Inrikes* / *Utrikes* | `wagecodeID` via `allowance_map`: inrikes / utrikes traktamente |
| Date | `date` | `date` | `date` |
| Description | `description` | `description` | `comment`, with the tag appended |
| Amount | `amount_ore`: the amount the source calculated for that day | allowance calculated by Kleer, per day | `price` = `amount_ore` / 100 / `quantity` |
| Full or half day | `quantity`: `1` or `0.5` (optional) | days and amounts as Kleer reports them | `quantity`, so the row total equals the source's amount |
| Re-invoiced to project | `project_id` | project the entry is re-invoiced to | `projectID` = `settings.project_id` |
| **Not replicated** | | | |
| Mileage | — (left out, named to the person) | expense report entry, kind `mileage` | *not replicated* |
| Absence | — (not exported) | absence | *not replicated* |
| **System behaviour** | | | |
| Version of the agent instructions | `playbook_version`; `sync.py` warns when it differs from what it expects | — | — |
| Reading and writing | — | read by the agent (MCP connector or API); never written | REST API, `api2.timekeeper.se` |
| Login | — | the agent's own connection | Basic Auth: `username` + keychain `password`; in a cloud session the cloud environment's network secret adds it ([cloud-sessions.md](cloud-sessions.md)) |
| Closed periods | — | — (only read) | per calendar month (`split_by_month`) |
| Row typed by hand | — | — (only read) | no tag in `comment`; never changed |
