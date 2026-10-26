#!/usr/bin/env python3
"""Turn a receipt returned by the source system's API into a real file.

Kleer's `getExpenseFileImage` (query `encoding=base64`) returns the receipt as base64 text.
Agent tools often store a large result in a file; this script decodes that file safely:

    python3 tools/save_receipt.py TOOL_RESULT_FILE receipts/<expense-id>.jpg

TOOL_RESULT_FILE may hold plain base64, a data: URI, or JSON containing the base64 string.
The output is only written if it really is a JPEG, PNG or PDF (magic bytes checked), so a
truncated or garbled result is reported instead of being uploaded to a target. The file
extension is corrected to what the data really is. Used by agents in cloud sessions, where
there is no receipt folder to ask the person about (docs/cloud-sessions.md).
"""
import base64
import binascii
import json
import os
import re
import sys

MAGIC = {b"\xff\xd8\xff": "jpg", b"\x89PNG\r\n\x1a\n": "png", b"%PDF-": "pdf"}


def longest_string(o):
    best = ""
    if isinstance(o, str):
        return o
    if isinstance(o, dict):
        o = list(o.values())
    if isinstance(o, list):
        for v in o:
            s = longest_string(v)
            if len(s) > len(best):
                best = s
    return best


def extract_b64(text: str) -> str:
    text = text.strip()
    if text[:1] in "{[":
        try:
            text = longest_string(json.loads(text))
        except json.JSONDecodeError:
            pass
    text = re.sub(r"^data:[^,]*,", "", text.strip())
    return re.sub(r"\s+", "", text)


def decode(text: str) -> tuple[bytes, str]:
    b64 = extract_b64(text)
    if len(b64) < 100:
        raise ValueError("no base64 payload found (too short)")
    try:
        raw = base64.b64decode(b64 + "=" * (-len(b64) % 4), validate=True)
    except (binascii.Error, ValueError) as e:
        raise ValueError(f"not valid base64 ({e}); the result may have been truncated")
    for magic, kind in MAGIC.items():
        if raw.startswith(magic):
            return raw, kind
    raise ValueError("decoded data is not a JPEG, PNG or PDF; the result may be truncated or garbled")


def main(argv) -> int:
    if len(argv) != 3:
        print(__doc__)
        return 2
    try:
        with open(argv[1], encoding="utf-8", errors="replace") as f:
            raw, kind = decode(f.read())
    except (OSError, ValueError) as e:
        print(f"ERROR   {e}")
        return 1
    out = argv[2]
    stem, ext = os.path.splitext(out)
    if ext.lower().lstrip(".") != kind and not (kind == "jpg" and ext.lower() == ".jpeg"):
        out = f"{stem}.{kind}"          # name the file by what it really is
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, "wb") as f:
        f.write(raw)
    print(f"saved {out} ({kind}, {len(raw)} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
