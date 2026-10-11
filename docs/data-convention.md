# Data convention

The week file is the only thing that crosses from the source side to the target side.
This page covers the source side (how the agent fills the week file) and the rules every
target follows to recognise its rows. How each target stores the data is on its own page
under [targets/](targets/).

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
| total incl. VAT | `amount_ore` | Integer, minor units (1/100 of the currency) |
| expense type | `expense_type` | Mapped per target by `expense_map` (type, else `default`) |
| project the entry is re-invoiced to | `project_id` | `null` if none |
| receipt exists | `has_receipt` | `true` → a confirmed local file is needed if a target takes receipts |
| confirmed file | `receipt_file` | Absolute path on the person's own machine |
| mileage / allowance entries | n/a | Not supported; left out and named to the person |

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
