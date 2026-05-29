import io
import unittest
from contextlib import redirect_stdout
from unittest import mock

from codex_mcp_clean import cli


class CliTests(unittest.TestCase):
    def test_version_does_not_touch_proc_guard(self):
        with mock.patch.object(cli.core, "ensure_linux_proc", side_effect=AssertionError("guard called")):
            output = io.StringIO()
            with self.assertRaises(SystemExit) as raised, redirect_stdout(output):
                cli.main(["--version"])

        self.assertEqual(raised.exception.code, 0)
        self.assertIn("codex-mcp-clean 0.1.0", output.getvalue())


if __name__ == "__main__":
    unittest.main()
