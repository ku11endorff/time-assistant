#!/usr/bin/env python3
"""time-assistant entry point: python3 sync.py --help

The code lives in the time_assistant/ package next to this file; this wrapper only
makes `python3 sync.py ...` work from any directory without installing anything.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from time_assistant.cli import main  # noqa: E402

if __name__ == "__main__":
    main()
