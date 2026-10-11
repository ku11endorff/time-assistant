import unittest

import _paths  # noqa: F401  (puts the repo root on sys.path)
from time_assistant import markers


class MarkerTests(unittest.TestCase):
    def test_tag_and_append(self):
        self.assertEqual(markers.tag("time", 7000001), "[ta:t:7000001]")
        self.assertEqual(markers.append("Taxi ", "expense", "5-1"), "Taxi [ta:e:5-1]")
        self.assertEqual(markers.append("", "time", 1), "[ta:t:1]")

    def test_find_respects_kind_and_reads_old_tags(self):
        self.assertEqual(markers.find("Planning [ta:t:42]", "time"), "42")
        self.assertIsNone(markers.find("Planning [ta:t:42]", "expense"))
        self.assertEqual(markers.find("Taxi [kleer:e:5-1]", "expense"), "5-1")
        self.assertIsNone(markers.find("typed by hand", "time"))
        self.assertIsNone(markers.find(None, "time"))

    def test_normalise_makes_old_and_new_tags_equal(self):
        self.assertEqual(markers.normalise("x [kleer:t:1] "), markers.normalise("x [ta:t:1]"))
        self.assertNotEqual(markers.normalise("x [kleer:t:1]"), markers.normalise("y [ta:t:1]"))


if __name__ == "__main__":
    unittest.main()
