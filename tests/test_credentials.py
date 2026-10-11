import subprocess
import unittest
from unittest import mock

import _paths  # noqa: F401  (puts the repo root on sys.path)
from time_assistant import credentials


def which(*present):
    return lambda name: f"/usr/bin/{name}" if name in present else None


class CredentialTests(unittest.TestCase):
    def test_env_name(self):
        self.assertEqual(credentials.env_name("my-client", "password"), "TA_MY_CLIENT_PASSWORD")

    def test_environment_variable_wins(self):
        with mock.patch.dict("os.environ", {"TA_CLIENT_PASSWORD": "from-env"}), \
                mock.patch("subprocess.run") as run:
            self.assertEqual(credentials.lookup("client", "password", interactive=False), "from-env")
            run.assert_not_called()

    def test_macos_keychain_per_target(self):
        done = subprocess.CompletedProcess([], 0, stdout="from-keychain\n", stderr="")
        with mock.patch.dict("os.environ", {}, clear=True), \
                mock.patch("shutil.which", which("security")), \
                mock.patch("subprocess.run", return_value=done) as run:
            self.assertEqual(credentials.lookup("partner", "password", interactive=False), "from-keychain")
        cmd = run.call_args[0][0]
        self.assertEqual(cmd, ["security", "find-generic-password", "-s", "time-assistant:partner",
                               "-a", "password", "-w"])

    def test_linux_secret_tool(self):
        done = subprocess.CompletedProcess([], 0, stdout="from-secret-tool", stderr="")
        with mock.patch.dict("os.environ", {}, clear=True), \
                mock.patch("shutil.which", which("secret-tool")), \
                mock.patch("subprocess.run", return_value=done) as run:
            self.assertEqual(credentials.lookup("client", "token", interactive=False), "from-secret-tool")
        self.assertEqual(run.call_args[0][0][-4:], ["service", "time-assistant:client", "account", "token"])

    def test_missing_secret_explains_how_to_store_it(self):
        not_found = subprocess.CompletedProcess([], 44, stdout="", stderr="not found")
        with mock.patch.dict("os.environ", {}, clear=True), \
                mock.patch("shutil.which", which("security")), \
                mock.patch("subprocess.run", return_value=not_found):
            with self.assertRaises(SystemExit) as e:
                credentials.lookup("client", "password", interactive=False)
        msg = str(e.exception)
        self.assertIn("security add-generic-password -s time-assistant:client -a password -U -w", msg)
        self.assertIn("TA_CLIENT_PASSWORD", msg)

    def test_prompt_when_interactive(self):
        with mock.patch.dict("os.environ", {}, clear=True), \
                mock.patch("shutil.which", which()), \
                mock.patch("getpass.getpass", return_value="typed"):
            self.assertEqual(credentials.lookup("client", "password", interactive=True), "typed")


if __name__ == "__main__":
    unittest.main()
