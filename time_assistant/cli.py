"""time-assistant: replicate an approved week of time and expense entries into one or
more target systems (first target: TimeKeeper).

Register once in your source system (reference: Kleer). Any AI agent (Claude, ChatGPT,
Microsoft Copilot, ...) or a person exports the week into a small JSON file
(schema/week.schema.json, procedure in docs/agent-playbook.md). This script validates
it, compares it with what each target already has, and creates or updates only what
differs, after you have seen a dry run.

Commands
  version                Show this version, the agent playbook it expects, and the git state.
  validate --week FILE   Check the week file's structure. No network access.
  check-config           Check config.json. No network access.
  targets                List the target types this version can write to.
  discover               Show the ids a target needs in config.json.
  plan  --week FILE      Dry run for every enabled target: what would change. Writes nothing.
  apply --week FILE      Perform the changes.
  migrate-config         Convert an old single-TimeKeeper config.json (keeps a backup).

Use --target NAME (repeatable) with discover/plan/apply to run only some targets.
Passwords and tokens never come from config.json: see time_assistant/credentials.py.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys

from . import __version__
from . import config as conf
from . import credentials, engine
from . import targets as registry
from . import week as weekfile


def default_connect(tcfg: dict):
    cls = registry.get(tcfg["type"])
    return cls(tcfg, credentials.get_secrets(tcfg["name"], cls.secrets))


def print_playbook_notice(week):
    notice = weekfile.playbook_notice(week)
    if notice:
        print(f"  WARN    {notice}\n")


def git_state() -> str | None:
    """`git describe` of the checkout this code runs from, if it is a git checkout."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    try:
        r = subprocess.run(["git", "-C", root, "describe", "--tags", "--always", "--dirty"],
                           capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return r.stdout.strip() if r.returncode == 0 and r.stdout.strip() else None


def cmd_version(_args):
    print(f"time-assistant {__version__}")
    print(f"agent playbook {weekfile.PLAYBOOK_VERSION}  (week files should carry "
          f"\"playbook_version\": {weekfile.PLAYBOOK_VERSION})")
    state = git_state()
    if state:
        print(f"git checkout   {state}")
    print("\nWhat changed: CHANGELOG.md   How to update: docs/updating.md")


def cmd_validate(args):
    week = weekfile.load(args.week)
    errs = weekfile.validate_week(week)
    if errs:
        print(f"{args.week}: {len(errs)} problem(s)")
        for e in errs:
            print(f"  ERROR   {e}")
        raise SystemExit(1)
    print_playbook_notice(week)
    print(f"{args.week}: valid ({len(week['time_events'])} time events, {len(week['expenses'])} expenses)")


def cmd_check_config(args):
    cfg = conf.load(args.config)
    for t in cfg["targets"]:
        state = "" if conf.enabled(t) else "  (disabled)"
        print(f"  {t['name']}: {registry.TARGETS[t['type']].display_name}, source projects "
              f"{', '.join(map(str, t['source_project_ids']))}{state}")
    for note in conf.feature_notes(cfg):
        print(f"  NOTE    {note}")
    print(f"{args.config}: valid ({len(cfg['targets'])} target(s))")


def cmd_targets(_args):
    print("Target types this version can write to:\n")
    for t, cls in sorted(registry.TARGETS.items()):
        caps = ["time"] + (["expenses"] if cls.supports_expenses else []) \
            + (["receipts"] if cls.supports_receipts else [])
        print(f"  {t:<14} {cls.display_name:<16} {', '.join(caps):<26} docs/targets/{t}.md")
    print("\nAdding another one: docs/adding-a-target.md")


def cmd_discover(args, connect):
    # Lenient on purpose: discover helps fill in the ids that the full check requires.
    cfg = conf.read(args.config)
    for tcfg in conf.select_targets(cfg, args.target):
        cls = registry.get(tcfg.get("type"))
        print(f"=== {tcfg.get('name')} ({cls.display_name}) ===")
        connect(tcfg).discover()
        print()


def cmd_sync(args, apply: bool, connect):
    cfg = conf.load(args.config)
    week = weekfile.load(args.week)
    problems = weekfile.validate_week(week)
    if problems:
        for p in problems:
            print(f"  ERROR   {p}")
        raise SystemExit(f"\n{args.week} is not a valid week file (see schema/week.schema.json). "
                         f"Nothing was written.")
    print_playbook_notice(week)
    code = engine.run(cfg, week, connect, names=args.target, apply=apply,
                      allow_missing_receipts=args.allow_missing_receipts)
    if code:
        raise SystemExit(code)


def cmd_migrate(args):
    path = args.config
    with open(path, encoding="utf-8") as f:
        old = json.load(f)
    if not conf.is_legacy(old):
        print(f"{path} is already in the current format; nothing to do.")
        return
    tk_user = os.path.join(os.path.dirname(os.path.abspath(path)), ".tk_user")
    username = ""
    if os.path.exists(tk_user):
        with open(tk_user, encoding="utf-8") as f:
            username = f.read().strip()
    new = conf.migrate(old, username)
    backup = path + ".bak-v1"
    n = 1
    while os.path.exists(backup):
        n += 1
        backup = f"{path}.bak-v1-{n}"
    shutil.copyfile(path, backup)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(new, f, indent=2, ensure_ascii=False)
        f.write("\n")
    t = new["targets"][0]
    print(f"Converted {path} (old version kept as {backup}).")
    print(f"It now has one target named '{t['name']}'; rename it if you like.\n")
    if not username:
        print("Fill in targets[0].username with your TimeKeeper login name.\n")
    print("The password is now looked up per target, so store it once more:")
    print(credentials.setup_hint(t["name"], "password"))
    print("\nRows already in TimeKeeper keep matching; they are not duplicated.")
    problems = conf.check(new)
    if problems:
        print("\nStill to fix in the new file:")
        for p in problems:
            print(f"  ERROR   {p}")


def main(argv=None, connect=None):
    connect = connect or default_connect
    ap = argparse.ArgumentParser(prog="sync.py", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default="config.json", help="default: config.json")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("version", help="show the version, the agent playbook it expects, and the git state")
    pv = sub.add_parser("validate", help="check a week file's structure, no network access")
    pv.add_argument("--week", required=True)
    sub.add_parser("check-config", help="check config.json, no network access")
    sub.add_parser("targets", help="list the target types this version can write to")
    pd = sub.add_parser("discover", help="show the ids a target needs in config.json")
    pd.add_argument("--target", action="append", metavar="NAME")
    for name in ("plan", "apply"):
        p = sub.add_parser(name, help="dry run" if name == "plan" else "write to the targets")
        p.add_argument("--week", required=True, help="week file exported by your agent")
        p.add_argument("--target", action="append", metavar="NAME",
                       help="only this target (repeatable); default: every enabled target")
        p.add_argument("--allow-missing-receipts", action="store_true",
                       help="warn instead of failing when a receipt in the source has no local file")
    sub.add_parser("migrate-config", help="convert an old single-TimeKeeper config.json")
    args = ap.parse_args(argv)

    if args.cmd == "version":
        cmd_version(args)
    elif args.cmd == "validate":
        cmd_validate(args)
    elif args.cmd == "check-config":
        cmd_check_config(args)
    elif args.cmd == "targets":
        cmd_targets(args)
    elif args.cmd == "discover":
        cmd_discover(args, connect)
    elif args.cmd == "migrate-config":
        cmd_migrate(args)
    else:
        cmd_sync(args, apply=(args.cmd == "apply"), connect=connect)


if __name__ == "__main__":
    main(sys.argv[1:])
