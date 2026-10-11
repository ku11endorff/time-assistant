# Data convention: source system ↔ TimeKeeper

Reference source system: **Kleer**. Every ID below is a made-up example; yours go into
`config.json` (see `config.example.json`).

## Time entries → `TimeRegistration`

| Source field (Kleer `listEvents`) | Meaning | TimeKeeper field | Rule |
|---|---|---|---|
| `id.id` | Event id | marker in `comment` | `[kleer:t:<id>]`. The key used to find, update and never duplicate the row |
| `date` | Work date | `date` | Copied as `yyyy-mm-dd` |
| `hours` | Decimal hours, e.g. `7.50` | `hours` + `minutes` | Split into whole hours and minutes (7.5 → 7 h 30 min) |
| `comment` | **External** comment | `comment` | Copied, marker appended. If empty: the `comment` text of the matching `time_map` entry if set, otherwise the marker only |
| `internal-comment` | Internal comment | n/a | Never exported, never copied |
| `activity.id` (e.g. 1001) | Source activity | `activityID` (e.g. 201) and `timeCodeID` (e.g. 301) | `config.json` → `time_map`. An unmapped activity is a blocking error |
| `client-project.id` (e.g. 1000001) | Source project | `projectID` (e.g. 5001) | Not mapped per row: one scope in `config.json` → `scope`. Every other project is ignored |
| (the user) | Source user | `userID` (e.g. 100) | `config.json` → `timekeeper_user_id` |
| `status.type` | `Open`, `Approved`, `Certified` | n/a | Approval gate only (`config.json` → `approval`). Not sent to TimeKeeper |
| `invoiceable`, `invoiced-*` | Source invoicing state | `isInvoiced` | Not forwarded, always `false` |
| the week | Monday–Sunday | n/a | Split by calendar month before posting |

## Expenses → `ExpenseRegistration`

| Source field (Kleer receipt entry) | Meaning | TimeKeeper field | Rule |
|---|---|---|---|
| `<expense nr>-<entry id>` | Entry id | marker in `comment` | `[kleer:e:<id>]` |
| `date` | Receipt date | `date` | Copied |
| `description` | Description | `comment` | Copied, marker appended |
| `amount_ore` | Total **incl. VAT**, minor units | `price`, `quantity` | `price = amount_ore / 100`, `quantity = 1` |
| `vat_ore` | VAT part | n/a | Not forwarded |
| `expense_type` | Expense type | `wagecodeID` | `config.json` → `expense_map` (per type, else `default`) |
| project the entry is re-invoiced to | Source project | `projectID` | Only entries on the configured project are replicated |
| receipt file | Receipt exists | file on the expense | The user-confirmed local file is uploaded to `/api/v1/File/ExpenseRegistrationFile` |
| mileage / allowance entries | | n/a | Not synced |

## Identity and idempotency

| Concept | Convention |
|---|---|
| Row identity | Marker at the end of the TimeKeeper comment: `[kleer:t:<id>]` for time, `[kleer:e:<id>]` for expenses |
| Re-run | Rows found by marker are updated if different and skipped if equal; nothing is duplicated |
| Manual TimeKeeper rows (no marker) | Never edited or deleted. WARN if one shares project and day with a synced row |
| Entry removed in the source | Kept in TimeKeeper with a WARN, unless `"delete_stale": true` |
| Month boundary | A week spanning two months is posted as two independent batches |

## Adding another source system

Only the *export* changes. Make your agent (or script) write the same week file
(`schema/week.schema.json`), keep the source's own approval wording in `status`, list the
accepted words in `config.json` → `approval.accepted_statuses`, and keep the `kleer_*`
config keys as the names for "source activity id / source project id". The marker prefix
`kleer:` is historical and stays as it is so existing rows keep matching.
