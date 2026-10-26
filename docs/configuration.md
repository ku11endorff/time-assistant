# config.json

Your private configuration: which targets receive which source projects, and how ids
map. Start from [`config.example.json`](../config.example.json); it is git-ignored once
copied to `config.json`. Check it any time, offline:

```bash
python3 sync.py check-config
```

Keys that start with `_` are notes for people and are ignored. Use straight quotes and
numeric ids.

## Top level

| Key | Required | Meaning |
|---|---|---|
| `version` | yes | `2` |
| `source.name` | no | How the source system is named in messages, e.g. `"Kleer"` |
| `source.rerun_hint` | no | Ends the "week not approved" error: *"Approve the week in Kleer, then &lt;rerun_hint&gt;."* Default `run the export again`. Put your own skill or command here |
| `approval.required` | no | `false` turns the week gate off. Default `true` |
| `approval.accepted_statuses` | no | Statuses that count as approved, copied from the source. Default `["Approved", "Certified"]` |
| `targets` | yes | One entry per system that receives copies |

## Each target

| Key | Required | Meaning |
|---|---|---|
| `name` | yes | Your label: lowercase letters, digits, `-`, `_`. Used in output, `--target`, and the keychain (`time-assistant:<name>`) |
| `type` | yes | Which system: see `python3 sync.py targets` |
| `source_project_ids` | yes | Source project ids (numbers) whose entries go to this target |
| `username` | if the type needs it | Login name; not a secret |
| `settings` | per type | Account and project ids in the target, e.g. TimeKeeper's `user_id` and `project_id` |
| `time_map` | yes | How source activities map to the target (below) |
| `expense_map` | no | How source expense types map (below). Leave it out (or empty) and this target's expenses are listed in the dry run but not written |
| `allowance_map` | no | How daily allowances (traktamente) map (below). Leave it out and allowances are listed but not written |
| `accepted_statuses` | no | Stricter approval for this target only, e.g. `["Certified"]` |
| `delete_stale` | no | `true` deletes rows whose source entry is gone. Default `false` (kept, with a WARN) |
| `enabled` | no | `false` skips the target unless named with `--target`. Default `true` |

The fields inside `settings`, `time_map`, `expense_map` and `allowance_map` depend on the
type; each target's page lists them: [TimeKeeper](targets/timekeeper.md).

### time_map

A list. Each entry maps one source activity (`source_activity_id`) to the target's own
codes. An entry without `source_activity_id` is the default for every other activity.
An optional `comment` is used when the source entry has no comment of its own.

```json
"time_map": [
  { "source_activity_id": 1001, "activity_id": 201, "timecode_id": 301 },
  { "activity_id": 202, "timecode_id": 302, "comment": "Consulting" }
]
```

An activity with no entry (and no default) is an error in the dry run, and nothing is
written until it is mapped.

### expense_map

An object from the source's expense type name (`expense_type` in the week file) to the
target's codes, with `"default"` for every other type.

```json
"expense_map": {
  "Taxi":    { "wagecode_id": 402 },
  "default": { "wagecode_id": 401, "receipt_category_id": 301, "paid_by": "self" }
}
```

Optional keys, for targets that record them (TimeKeeper does, see
[its page](targets/timekeeper.md#receipt-category-and-paid-by)):

| Key | Meaning |
|---|---|
| `receipt_category_id` | The target's receipt category ("Kategori"). Some accounts refuse the receipt wage code without one |
| `paid_by` | `"self"` (paid by you, to be reimbursed) or `"company"` (paid by the company, e.g. a company card) |

The week file's `vat_ore`, when present, is sent as the VAT amount; no config is needed.

### allowance_map

Daily allowances (traktamente) are expense entries with `"kind": "allowance"` in the week
file. They are mapped by trip type, never by `expense_map`, and never fall back to its
`default`:

```json
"allowance_map": {
  "domestic": { "wagecode_id": 501 },
  "foreign":  { "wagecode_id": 502 }
}
```

`domestic` is a trip within the country (inrikes), `foreign` a trip abroad (utrikes). A
type without an entry is listed in the dry run as not replicated, so map only what the
target should receive. A target type that cannot store allowances refuses the key in
`check-config`.

## Secrets

Cloud sessions use none of this: see [Cloud sessions](#cloud-sessions) below.

Passwords and tokens never go into `config.json`. For target `client` and secret
`password`, `sync.py` looks in this order:

1. environment variable `TA_CLIENT_PASSWORD`
2. macOS keychain: service `time-assistant:client`, account `password`
3. Linux secret service (`secret-tool`): same service and account
4. a hidden prompt, when run in a terminal

Store it once:

```bash
security add-generic-password -s time-assistant:client -a password -U -w      # macOS
secret-tool store --label=time-assistant:client service time-assistant:client account password   # Linux
```

## Cloud sessions

In a cloud session (phone, web) there is no `config.json` file, no keychain and no password
to look up. Two environment variables replace them
([cloud-sessions.md](cloud-sessions.md) has the full setup):

| Variable | Content |
|---|---|
| `TIME_ASSISTANT_AUTH` | `proxy`: the login is added to the target's requests by the cloud environment's network secret, outside the session. `username` is then not required in `config.json` |
| `TIME_ASSISTANT_CONFIG_JSON` | The contents of `config.json` (ids only, no secrets), used when the file `config.json` does not exist. A file always wins |

`python3 tools/make_cloud_env.py` writes both lines from your `config.json`.

## Converting the old format

Configs from the single-TimeKeeper version (with `scope` and `timekeeper_user_id`) are
refused with a pointer to:

```bash
python3 sync.py migrate-config
```

It writes the new format into `config.json`, keeps the old file as `config.json.bak-v1`,
reads your username from `.tk_user` if present, and prints the keychain command for the
password under its new name.
