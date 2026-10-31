# Getting started

From nothing to a first replicated week, step by step. Every id on this page is a made-up
example; yours come from your own Kleer and TimeKeeper.

**Prefer a page you can click through?** Open [`guide.html`](guide.html) in a browser: it works
offline, lets you pick your route, tick off the steps, and builds your `config.json` from the
ids you collect. Nothing you type leaves the page.

**Want to be guided interactively in Claude?** Install the setup skill ([step 0](#0-optional-let-claude-guide-you))
and say *"Guide me through time-assistant setup"*. It walks you through this same page one
step at a time, runs the commands it can, and waits for you where only you can act. Any other
AI agent can do the same if you paste [`integrations/claude/time-assistant-setup/SKILL.md`](../integrations/claude/time-assistant-setup/SKILL.md)
into its instructions.

First read [how-it-works.md](how-it-works.md) if you have not yet; five minutes there saves
questions here.

## Choose your route

| Route | You work from | Login is kept in | Best if | Guide |
|---|---|---|---|---|
| **A. On your computer** | Terminal on macOS or Linux, any AI agent that can read Kleer | OS keychain | You have a computer at hand when you replicate | This page, then [claude-project-setup.md](claude-project-setup.md) for the Claude routine |
| **B. From your phone or the web** | A Claude Code cloud session on a private copy of this repository | The cloud environment's network secret | You want to replicate from anywhere, without a computer | [cloud-sessions.md](cloud-sessions.md) |

You can set up route A first and add B later; they share the same `config.json` content.

## What you need before you start

| Need | Why | Check |
|---|---|---|
| Access to **Kleer**, and an AI agent that can read it (for Claude: the Kleer connector) | The agent reads your approved week | Ask the agent: *"Who am I in Kleer?"* |
| A **TimeKeeper** login with API access, and the project you replicate into | `sync.py` writes there | You can log in; `discover` (step 4) lists your project. If it says 401/403, ask your TimeKeeper administrator whether the API is enabled for you |
| **Python 3.9 or newer** (standard library only) | Runs `sync.py` | `python3 --version` |
| **git** | Get the code and updates | `git --version` |
| The **Kleer project(s)** you replicate, and the matching TimeKeeper project(s) | Decides what goes where | You know which client or assignment each one is |

Decide this first, it drives the config: **which Kleer project goes to which TimeKeeper
project?** One Kleer project can go to several targets (for example the client's TimeKeeper
and a partner's); each target is its own entry in `config.json`.

## 0. Optional: let Claude guide you

```bash
git clone https://github.com/<you>/time-assistant.git
cd time-assistant
mkdir -p ~/.claude/skills
ln -sfn "$PWD/integrations/claude/time-assistant-setup" ~/.claude/skills/time-assistant-setup
ln -sfn "$PWD/integrations/claude/time-assistant"       ~/.claude/skills/time-assistant
```

Open Claude in this folder and say *"Guide me through time-assistant setup"*. The first skill
is the guide, the second is the weekly export. Skipping this step is fine; the rest of this
page is the same procedure to do by hand.

## 1. Get the code

```bash
git clone https://github.com/<you>/time-assistant.git      # skip if you did it above
cd time-assistant
python3 sync.py version
python3 -m unittest discover -s tests -p "test_*.py"       # optional: offline self-test
```

## 2. Create your configuration

```bash
cp config.example.json config.json
```

`config.json` is git-ignored: it holds your ids and never leaves your machine. Open it and
fill in, in this order. Steps 3 and 4 give you the ids.

| Field | What to put | How to find it |
|---|---|---|
| `source.name` | `Kleer` | |
| `targets[0].name` | A short name for this target, lowercase, e.g. `client` | You choose |
| `targets[0].username` | Your TimeKeeper login name (not a secret) | |
| `targets[0].source_project_ids` | The Kleer project id(s) this target receives | [Step 3](#3-find-your-kleer-ids) |
| `settings.user_id`, `settings.project_id` | Your TimeKeeper user and project | [Step 4](#4-store-the-login-and-find-your-timekeeper-ids) |
| `time_map` | Kleer activity → TimeKeeper activity and time code | Steps 3 and 4 |
| `expense_map` | Kleer expense type → wage code, receipt category, paid by | Step 4 |
| `allowance_map` | Optional: wage codes for domestic and foreign traktamente | Step 4 |

Field reference: [configuration.md](configuration.md).

## 3. Find your Kleer ids

Ask your agent, or read them from Kleer's data. With the Kleer connector the agent can do
all of this for you: *"Read my time entries and expenses for last week and list the project
ids, activity ids and expense types you find."*

| You need | Where it is in Kleer's data | Goes into |
|---|---|---|
| The **client-project id** of your project | `client-project.id` on a time entry (`listEvents`) | `source_project_ids` |
| The **expense project id** (differs from the one above!) | `re_invoice_project.id` on an expense entry (`get_expense`). A new one may appear per expense | `source_project_ids`, **in addition** to the client-project id, once you have confirmed it is the same project |
| The **activity id** of your time entries | `activity.id` on a time entry | `time_map[].source_activity_id` |
| The **expense type** names you use | `expense_type.name` on an expense entry | `expense_map` keys (or just `default`) |

Why two project ids? See [how-it-works.md](how-it-works.md#things-about-kleer-that-surprise-people).
If you are unsure whether two ids are the same project, compare their names in Kleer; the
agent can show both.

## 4. Store the login and find your TimeKeeper ids

Store the TimeKeeper password for the target (it prompts you; nothing is saved in a file, and
the AI never sees it):

```bash
security add-generic-password -s time-assistant:client -a password -U -w          # macOS
secret-tool store --label=time-assistant:client service time-assistant:client account password   # Linux
```

Use your target's `name` in place of `client`. Then:

```bash
python3 sync.py discover
```

It prints your user, ongoing projects, activities, time codes, receipt categories and wage
codes. Copy the ids into `config.json`:

| `discover` section | config.json |
|---|---|
| `/Login/me` → `id` | `settings.user_id` |
| Projects: the **first column** (internal id, not the project number) | `settings.project_id` |
| Activities, Time codes | `time_map[].activity_id`, `time_map[].timecode_id` (the time code that belongs to the activity) |
| Wage codes: the one named *Kvitto* (or your receipt code) | `expense_map.default.wagecode_id` |
| Receipt categories (use an **active** one) | `expense_map.default.receipt_category_id` |
| (you decide) | `expense_map.default.paid_by`: `"self"` if you pay and are reimbursed, `"company"` for a company card |
| Wage codes: inrikes and utrikes traktamente | `allowance_map.domestic.wagecode_id`, `allowance_map.foreign.wagecode_id` (leave out to not replicate allowances) |

If `discover` cannot list wage codes, enter one expense by hand in TimeKeeper once and copy
`wageCodeID` from that row, or ask your TimeKeeper administrator.

## 5. Check the configuration

```bash
python3 sync.py check-config
```

`ERROR` lines must be fixed. `NOTE` lines are optional features you have not switched on
(for example receipt category, or allowances).

## 6. Check the week file side

```bash
python3 sync.py validate --week examples/week.example.json
python3 sync.py validate --week examples/week.example-expenses.json
```

Both should say `valid`. They are examples with made-up ids; do not `apply` them.

## 7. Give your agent its instructions

The agent follows [`docs/agent-playbook.md`](agent-playbook.md), distributed in the format
each tool reads ([agents.md](agents.md)). For Claude the whole routine is in
[claude-project-setup.md](claude-project-setup.md), including a Claude project that holds
your instructions and the Kleer connection.

## 8. Your first real week

1. In Kleer, register and **approve** a week.
2. Ask the agent: *"Export last week for time-assistant."* It must name the exact dates,
   stop if anything is not approved, deal with receipts, and write `week-YYYY-Www.json`.
3. `python3 sync.py plan --week week-YYYY-Www.json` and read every line. Is each day and
   amount what you expect? Anything under `WARN` or `ERROR`?
4. `python3 sync.py apply --week week-YYYY-Www.json`
5. Run `plan` again: everything should say `unchanged`. Open TimeKeeper and look at the
   rows once yourself, including the attached receipt.

**First time with a new setup, replicate a quiet week or a single day first**, and look at
the result in TimeKeeper before you trust it with a full month.

## Every week from now on

1. Register your time and expenses in Kleer; get the week approved.
2. *"Export last week for time-assistant."*
3. `plan`, read, `apply`, `plan` again. (macOS: double-click `Sync.command` for the same with
   a prompt in between.)

## Adding things later

| I want to... | Do |
|---|---|
| Replicate a second Kleer project into the same TimeKeeper project | Add its id to `source_project_ids` and its activity to `time_map` |
| Send the week to a second TimeKeeper (partner, another client) | Add another entry under `targets` with its own name, login and `settings`; store its password under its own name. See [examples/config.two-targets.example.json](../examples/config.two-targets.example.json) |
| Receive allowances | Add `allowance_map`, [configuration.md](configuration.md#allowance_map) |
| Use it from my phone | [cloud-sessions.md](cloud-sessions.md) |
| Update to a new version | [updating.md](updating.md) |

## If something goes wrong

| Symptom | First thing to try |
|---|---|
| `No password found for target` | Store it again, step 4 |
| `config.json has N problem(s)` | Fix what the list says; `check-config` re-checks |
| `HTTP 401` from TimeKeeper | Wrong username or password; store the password again |
| `HTTP 403` for one month | The period is closed in TimeKeeper; the other month is still written |
| `WEEK NOT APPROVED` | Approve the week in Kleer, export again |
| An expense is "not replicated" | Its project id is missing from `source_project_ids` |
| `HTTP 400 ... Lönekoden Kvitto` | Set `receipt_category_id` and `paid_by`, step 4 |
| Anything else | The troubleshooting table in the [README](../README.md#troubleshooting) and [targets/timekeeper.md](targets/timekeeper.md#troubleshooting) |
