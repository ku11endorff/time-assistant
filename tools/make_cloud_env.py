#!/usr/bin/env python3
"""Write cloud-environment-variables.txt from config.json (ids only, no password).

    python3 tools/make_cloud_env.py [config.json]

Paste the two lines into the cloud environment's "Environment variables" box
(docs/cloud-sessions.md). Notes (keys starting with "_") are dropped. The output file is
git-ignored. The login itself is NOT part of it: it goes into the environment's network
secret, which neither you nor the agent ever puts in a file.
"""
import json
import sys


def strip(o):
    if isinstance(o, dict):
        return {k: strip(v) for k, v in o.items() if not k.startswith("_")}
    if isinstance(o, list):
        return [strip(v) for v in o]
    return o


def build(cfg: dict) -> str:
    line = json.dumps(strip(cfg), separators=(",", ":"), ensure_ascii=False)
    if "'" in line:
        raise ValueError("The config contains a single quote, which would break the line. Remove it.")
    return f"TIME_ASSISTANT_AUTH=proxy\nTIME_ASSISTANT_CONFIG_JSON='{line}'\n"


def main(argv) -> int:
    path = argv[1] if len(argv) > 1 else "config.json"
    with open(path, encoding="utf-8") as f:
        cfg = json.load(f)
    try:
        text = build(cfg)
    except ValueError as e:
        print(f"ERROR   {e}")
        return 1
    with open("cloud-environment-variables.txt", "w", encoding="utf-8") as f:
        f.write(text)
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
