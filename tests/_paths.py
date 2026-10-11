"""Makes the tests runnable from any directory: puts the repo root on sys.path."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXAMPLE_WEEK = os.path.join(ROOT, "examples", "week.example.json")
EXAMPLE_CONFIG = os.path.join(ROOT, "config.example.json")
TWO_TARGETS_CONFIG = os.path.join(ROOT, "examples", "config.two-targets.example.json")
FIXTURES = os.path.join(ROOT, "tests", "fixtures")
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
