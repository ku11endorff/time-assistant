import io
import unittest
import urllib.error
from unittest import mock

import _paths  # noqa: F401  (puts the repo root on sys.path)
import sync


def http_error(code):
    return urllib.error.HTTPError("http://x", code, "err", {}, io.BytesIO(b'{"title":"Not Found"}'))


class Http404Tests(unittest.TestCase):
    def setUp(self):
        self.tk = sync.TimeKeeper("u", "p", "https://example.invalid")

    def test_404_on_registration_list_means_empty(self):
        with mock.patch("urllib.request.urlopen", side_effect=http_error(404)):
            self.assertEqual(self.tk.time_regs(1, "2026-10-12", "2026-10-12"), [])
            self.assertEqual(self.tk.expense_regs(1, "2026-10-12", "2026-10-12"), [])

    def test_404_on_a_write_still_fails_loudly(self):
        with mock.patch("urllib.request.urlopen", side_effect=http_error(404)):
            with self.assertRaises(SystemExit):
                self.tk.create_time({"userID": 1})

    def test_other_errors_on_lists_still_fail(self):
        with mock.patch("urllib.request.urlopen", side_effect=http_error(401)):
            with self.assertRaises(SystemExit):
                self.tk.time_regs(1, "2026-10-12", "2026-10-12")


if __name__ == "__main__":
    unittest.main(verbosity=2)
