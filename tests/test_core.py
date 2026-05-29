import unittest

from codex_mcp_clean import core


def proc(pid, ppid, argv, name=None, start_ts=0, rss_kb=0, pss_kb=0):
    argv = list(argv)
    return core.ProcessInfo(
        pid=pid,
        ppid=ppid,
        name=name or (argv[0].split("/")[-1] if argv else ""),
        argv=argv,
        cmdline=" ".join(argv),
        start_ts=start_ts,
        rss_kb=rss_kb,
        pss_kb=pss_kb,
    )


class PlatformGuardTests(unittest.TestCase):
    def test_linux_proc_guard_accepts_linux_proc(self):
        core.ensure_linux_proc(platform="linux", proc_root_exists=True)

    def test_linux_proc_guard_rejects_non_linux(self):
        with self.assertRaisesRegex(SystemExit, "Linux-only"):
            core.ensure_linux_proc(platform="win32", proc_root_exists=True)

    def test_linux_proc_guard_rejects_missing_proc(self):
        with self.assertRaisesRegex(SystemExit, "/proc"):
            core.ensure_linux_proc(platform="linux", proc_root_exists=False)


class ProcessDetectionTests(unittest.TestCase):
    def test_detects_codex_app_server(self):
        process = proc(10, 1, ["/opt/codex", "app-server", "--analytics-default-enabled"])

        self.assertTrue(core.is_codex_appserver(process))

    def test_launcher_detection_is_specific(self):
        real_remote = proc(20, 10, ["npm", "exec", "mcp-remote", "https://example.invalid"], name="npm exec mcp-re")
        real_telegram = proc(21, 10, ["/x/mcp-telegram", "serve"], name="mcp-telegram")
        real_serena = proc(22, 10, ["/x/uv", "tool", "uvx", "--from", "git+https://github.com/oraios/serena", "serena"])
        real_context7 = proc(23, 10, ["npx", "-y", "@upstash/context7-mcp"], name="npm exec @upsta")
        real_playwright = proc(24, 10, ["npm", "exec", "@playwright/mcp@latest"], name="npm exec @playw")
        real_slack = proc(25, 10, ["npm", "exec", "@jtalk/slack-mcp"], name="npm exec @jtalk")
        noisy_shell = proc(26, 10, ["bash", "-lc", "echo context7 playwright mcp-remote serena"], name="bash")

        self.assertEqual(core.mcp_launcher_kind(real_remote), "youtrack/mcp-remote")
        self.assertEqual(core.mcp_launcher_kind(real_telegram), "telegram")
        self.assertEqual(core.mcp_launcher_kind(real_serena), "serena")
        self.assertEqual(core.mcp_launcher_kind(real_context7), "context7")
        self.assertEqual(core.mcp_launcher_kind(real_playwright), "playwright")
        self.assertEqual(core.mcp_launcher_kind(real_slack), "slack")
        self.assertIsNone(core.mcp_launcher_kind(noisy_shell))

    def test_cleanup_set_is_limited_to_root_pid_since_and_direct_launchers(self):
        processes = {
            100: proc(100, 1, ["/opt/codex", "app-server"], name="codex", start_ts=1),
            200: proc(200, 1, ["/opt/codex", "app-server"], name="codex", start_ts=1),
            110: proc(110, 100, ["npm", "exec", "mcp-remote"], name="npm exec mcp-re", start_ts=5),
            111: proc(111, 110, ["sh", "-c", "node mcp-remote"], name="sh", start_ts=6),
            112: proc(112, 111, ["node", "mcp-remote"], name="node", start_ts=7),
            120: proc(120, 100, ["/x/mcp-telegram", "serve"], name="mcp-telegram", start_ts=20),
            121: proc(121, 120, ["python", "telegram-child"], name="python", start_ts=21),
            130: proc(130, 100, ["bash", "-lc", "echo mcp-remote"], name="bash", start_ts=22),
            131: proc(131, 130, ["/x/mcp-telegram", "serve"], name="mcp-telegram", start_ts=23),
            210: proc(210, 200, ["/x/mcp-telegram", "serve"], name="mcp-telegram", start_ts=20),
        }

        killset, launchers = core.compute_cleanup_set(processes, root_pid=100, since_ts=10)

        self.assertEqual(killset, {120, 121})
        self.assertEqual([(item.pid, item.kind) for item in launchers], [(120, "telegram")])


if __name__ == "__main__":
    unittest.main()
