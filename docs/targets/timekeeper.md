# Target: TimeKeeper

`"type": "timekeeper"` writes time and expense registrations, with receipt files, into
[TimeKeeper](https://www.timekeeper.se) through its REST API (`api2.timekeeper.se`).

| | |
|---|---|
| Time | ✓ `TimeRegistration` |
| Expenses | ✓ `ExpenseRegistration` |
| Receipts | ✓ uploaded to `/api/v1/File/ExpenseRegistrationFile` |
| Month split | yes: each calendar month is written and verified separately |
| Login | Basic Auth: `username` in config.json, `password` in the keychain |
| Status | beta: reading and dry runs are used for real; expense writes and receipt upload are tested offline against a fake TimeKeeper |

## Setup

1. Add a target to `config.json` (copy the one in `config.example.json`) with your
   TimeKeeper login as `username`.
2. Store the password under the target's name, e.g. for a target named `client`:

   ```bash
   security add-generic-password -s time-assistant:client -a password -U -w
   ```

3. Run `python3 sync.py discover --target client`. It prints your user, the ongoing
   projects, activities and time codes. Fill in:

   | config.json | From `discover` |
   |---|---|
   | `settings.user_id` | `id` under `/Login/me` |
   | `settings.project_id` | the **first column** of the project list: the internal id, not the project number |
   | `time_map[].activity_id` | the activity |
   | `time_map[].timecode_id` | the time code that belongs to that activity |
   | `expense_map.*.wagecode_id` | not listed by the API: copy `wagecodeID` from an existing expense row, or ask your TimeKeeper administrator |

4. Optional: `settings.base_url` if your TimeKeeper is not on `https://api2.timekeeper.se`.
5. `python3 sync.py check-config`.

```json
{
  "name": "client",
  "type": "timekeeper",
  "username": "you@example.com",
  "source_project_ids": [1000001],
  "settings": { "user_id": 100, "project_id": 5001 },
  "time_map": [ { "source_activity_id": 1001, "activity_id": 201, "timecode_id": 301 } ],
  "expense_map": { "default": { "wagecode_id": 401 } }
}
```

## Field mapping

### Time entry → `TimeRegistration`

| Week file | TimeKeeper | Rule |
|---|---|---|
| `id` | tag in `comment` | `[ta:t:<id>]`, the key used to find, update and never duplicate the row |
| `date` | `date` | Copied |
| `hours` | `hours` + `minutes` | 7.5 → 7 h 30 min |
| `comment` | `comment` | Copied, tag appended. Empty → the `time_map` entry's `comment`, else the tag only |
| `activity_id` | `activityID`, `timeCodeID` | Via `time_map` |
| (target) | `projectID`, `userID` | `settings.project_id`, `settings.user_id` |
| | `isInvoiced` | Always `false`; the source's invoicing state is not forwarded |

### Expense → `ExpenseRegistration`

| Week file | TimeKeeper | Rule |
|---|---|---|
| `id` | tag in `comment` | `[ta:e:<id>]` |
| `date` | `date` | Copied |
| `description` | `comment` | Copied, tag appended |
| `amount_ore` | `price`, `quantity` | `price = amount_ore / 100`, `quantity = 1` |
| `expense_type` | `wagecodeID` | Via `expense_map` (type, else `default`) |
| `receipt_file` | attached file | Uploaded once; a file with the same name is not uploaded again |

## Behaviour worth knowing

- **Only its own project.** The target reads and compares only rows in
  `settings.project_id`. Two targets in the same TimeKeeper account must use different
  projects (`check-config` refuses otherwise). If you change `project_id`, rows already
  in the old project are left there and new ones are created in the new project.
- **Empty periods.** TimeKeeper answers HTTP 404 when a registration list is empty; that is
  read as "no rows yet". A 404 on a write still fails loudly.
- **Rate limits.** Writes are spaced by 0.2 s; HTTP 429/502/503/504 are retried twice.
- **Rows typed by hand** (no tag) are never changed; one on the same project and day as a
  new row is flagged as a possible double entry.
- **Old tags.** Rows written before targets became pluggable carry `[kleer:t:<id>]`. They
  still match and are only rewritten (with the new tag) when something else changed.

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `TimeKeeper GET ... -> HTTP 401` | Wrong username or password. Re-store the password for this target |
| `settings.project_id` seems right but rows go nowhere | You used the project *number*; `discover` shows the internal id in the first column |
| `TimeKeeper POST ... -> HTTP 403` for one month | The period is closed in TimeKeeper; the other month is still written |
| `file not found ... not downloaded to this Mac` | The receipt is an iCloud placeholder; download it in Finder first |
