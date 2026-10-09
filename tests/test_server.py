"""Test del server con i comandi di Windows simulati: girano su qualsiasi sistema.

Nati dalla revisione del 9 ottobre 2026 (16 prove che riproducevano difetti), riscritti per
verificare il comportamento corretto. Avvio: python -m unittest discover -s tests -v
"""
import copy
import datetime as dt
import hashlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SANDBOX = tempfile.TemporaryDirectory(prefix="agg-test-")
os.environ["LOCALAPPDATA"] = SANDBOX.name
sys.path.insert(0, str(ROOT))
import server as s  # noqa: E402

INITIAL = copy.deepcopy(s.state)
ITEM = dict(id="winget:Vendor.App", key="winget:Vendor.App", token="Vendor.App", name="App",
            installed="1.0", latest="1.1", location="C:\\Apps\\App", verified=True, major=False,
            source="winget")
PROC = dict(id=123, path="C:\\Apps\\App\\app.exe", window=True)


def table(header, rows, width=90):
    return "\n".join([header, "-" * width] + rows)


class Base(unittest.TestCase):
    def setUp(self):
        s.state.clear()
        s.state.update(copy.deepcopy(INITIAL))
        s.state["items"] = [dict(ITEM)]
        s.state["jobs"][ITEM["id"]] = dict(status="running", log="", phase=None, pct=None)
        s._arp.clear()
        for p in (s.SETTINGS_FILE, s.EXCLUDED_FILE, getattr(s, "HISTORY_FILE", s.SETTINGS_FILE)):
            Path(p).unlink(missing_ok=True)


class Scan(Base):
    def test_failed_scan_is_an_error_and_keeps_last_list(self):
        s.state["scanning"] = True
        with patch.object(s, "run", return_value=(1, "Source unavailable")), \
             patch.object(s, "powershell", return_value=(1, "failure")), \
             patch.object(s, "check_self_update"), patch.object(s, "extract_icons", return_value={}):
            s.do_scan()
        self.assertIn("Source unavailable", s.state["scan_error"])
        self.assertTrue(s.state["stale"])
        self.assertEqual(s.state["items"][0]["id"], ITEM["id"])   # ultimo elenco valido conservato

    def test_no_updates_answer_is_not_an_error(self):
        rows, err = (lambda: None, None)
        with patch.object(s, "run", return_value=(0x8A15002B, "Nessun aggiornamento disponibile.")):
            rows, err = s.winget_query(["upgrade"])
        self.assertEqual((rows, err), ([], None))

    def test_windows_update_failure_is_not_empty_list(self):
        with patch.object(s, "powershell", return_value=(1, "")):
            self.assertIsNone(s.scan_windows_update())


class Parser(Base):
    def test_four_columns_with_source(self):
        out = s.parse_table(table(f'{"Name":25}{"Id":25}{"Version":15}Source',
                                  [f'{"App":25}{"Vendor.App":25}{"1.0":15}winget']))
        self.assertEqual((out[0]["source"], out[0]["available"]), ("winget", ""))

    def test_four_columns_with_available(self):
        out = s.parse_table(table(f'{"Name":25}{"Id":25}{"Version":15}Available',
                                  [f'{"App":25}{"Vendor.App":25}{"1.0":15}1.1']))
        self.assertEqual((out[0]["available"], out[0]["source"]), ("1.1", ""))

    def test_name_starting_with_number_is_kept(self):
        out = s.parse_table(table(f'{"Name":25}{"Id":25}{"Version":15}{"Available":15}Source',
                                  [f'{"123 App":25}{"Vendor.App":25}{"1.0":15}{"1.1":15}winget',
                                   "1 aggiornamenti disponibili."]))
        self.assertEqual([r["name"] for r in out], ["123 App"])


class Queue(Base):
    def test_unexpected_error_never_leaves_program_busy(self):
        s.state["running"] = True
        with patch.object(s, "running_in", side_effect=subprocess.TimeoutExpired("powershell", 60)), \
             patch.object(s, "cleanup"):
            s.do_updates({ITEM["id"]})
        self.assertFalse(s.state["running"])
        self.assertEqual(s.state["jobs"][ITEM["id"]]["status"], "error")

    def test_reopen_failure_keeps_successful_update(self):
        with patch.object(s, "running_in", return_value=[PROC]), patch.object(s, "close_apps", return_value="closed"), \
             patch.object(s, "run_stream", return_value=(0, "Success")), \
             patch.object(s, "reopen", side_effect=OSError("explorer failed")):
            s.update_one(ITEM)
        self.assertEqual(s.state["jobs"][ITEM["id"]]["status"], "done")

    def test_stop_finishes_current_and_skips_rest(self):
        second = dict(ITEM, id="winget:Other.App", key="winget:Other.App", token="Other.App", name="Other")
        s.state["items"].append(second)
        s.state["running"] = True

        def fake_update(item, mode):
            s.state["stop"] = True   # "Interrompi" premuto durante la prima installazione
            s.state["jobs"][item["id"]]["status"] = "done"
        with patch.object(s, "update_one", side_effect=fake_update) as up, patch.object(s, "cleanup"):
            s.do_updates({ITEM["id"], second["id"]})
        self.assertEqual(up.call_count, 1)
        self.assertNotIn(second["id"], s.state["jobs"])   # torna tra quelli da fare
        self.assertFalse(s.state["running"])

    def test_update_pins_version_and_source(self):
        with patch.object(s, "running_in", return_value=[]), \
             patch.object(s, "run_stream", return_value=(0, "")) as run:
            s.update_one(ITEM)
        cmd = run.call_args.args[0]
        self.assertEqual(cmd[cmd.index("--version") + 1], "1.1")
        self.assertEqual(cmd[cmd.index("--source") + 1], "winget")

    def test_output_without_final_newline_is_kept(self):
        lines = []
        rc, out = s.run_stream([sys.executable, "-c", "import sys; sys.stdout.write('important error')"], lines.append)
        self.assertEqual((rc, out, lines), (0, "important error", ["important error"]))


class Closing(Base):
    def test_open_save_dialog_is_never_force_closed(self):
        with patch.object(s, "window_titles", return_value=["Document - Editor", "Save changes?"]), \
             patch.object(s, "pid_alive", return_value=True), patch.object(s.time, "sleep"), \
             patch.object(s, "powershell", return_value=(0, "")) as ps:
            result = s.close_apps([PROC], lambda text: None)
        self.assertEqual(result, "open")
        self.assertFalse(any("-Force" in c.args[0] for c in ps.call_args_list))

    def test_window_inspection_failure_is_not_force_closed(self):
        with patch.object(s, "window_titles", side_effect=RuntimeError("no access")), \
             patch.object(s, "pid_alive", return_value=True), patch.object(s.time, "sleep"), \
             patch.object(s, "powershell", return_value=(0, "")) as ps:
            self.assertEqual(s.close_apps([PROC], lambda text: None), "open")
        ps.assert_not_called()

    def test_unclosed_app_becomes_blocked_for_user_choice(self):
        with patch.object(s, "running_in", return_value=[PROC]), patch.object(s, "close_apps", return_value="open"), \
             patch.object(s, "run_stream") as run:
            s.update_one(ITEM)
        run.assert_not_called()
        self.assertEqual(s.state["jobs"][ITEM["id"]]["status"], "blocked")

    def test_auto_mode_postpones_app_opened_after_precheck(self):
        with patch.object(s, "running_in", return_value=[PROC]), patch.object(s, "close_apps") as close, \
             patch.object(s, "run_stream") as run:
            s.update_one(ITEM, mode="auto")
        close.assert_not_called()
        run.assert_not_called()
        self.assertEqual(s.state["jobs"][ITEM["id"]]["status"], "postponed")


class Schedule(Base):
    def test_nightly_update_not_due_at_noon(self):
        self.assertFalse(s.due("03:00", "2026-10-08", dt.datetime(2026, 10, 9, 12, 0), s.NIGHT_WINDOW_HOURS))
        self.assertTrue(s.due("03:00", "2026-10-08", dt.datetime(2026, 10, 9, 6, 30), s.NIGHT_WINDOW_HOURS))

    def test_busy_program_does_not_consume_the_night(self):
        s.update_settings(lambda st: st.update(auto_update=True, auto_time="03:00"))
        night = dt.datetime(2026, 10, 9, 3, 5)
        with patch.object(s, "auto_update", return_value=False), \
             patch.object(s.dt, "datetime", wraps=dt.datetime) as fake_dt, \
             patch.object(s.time, "sleep", side_effect=[None, KeyboardInterrupt]):
            fake_dt.now.return_value = night
            with self.assertRaises(KeyboardInterrupt):
                s.scheduler()
        self.assertIsNone(s.load_settings()["last_auto_day"])


class SelfUpdate(Base):
    def _run(self, exe, payload, published_hash, replace=None):
        s.state["self"].update(latest="9.9.9", assets={s.exe_asset_name(): "https://x/exe",
                                                       s.exe_asset_name() + ".sha256": "https://x/sha"})

        def opener(req, timeout=0):
            url = req.full_url if hasattr(req, "full_url") else req
            return io.BytesIO(f"{published_hash}  file\n".encode() if url.endswith("sha") else payload)
        patches = [patch.object(s, "install_method", return_value="exe"), patch.object(sys, "executable", str(exe)),
                   patch.object(s.urllib.request, "urlopen", side_effect=opener), patch.object(s, "restart_server")]
        if replace:
            patches.append(patch.object(os, "replace", side_effect=replace))
        for p in patches:
            p.start()
        try:
            s.do_self_update()
        finally:
            for p in reversed(patches):
                p.stop()

    def test_rejects_file_not_matching_published_checksum(self):
        with tempfile.TemporaryDirectory(dir=SANDBOX.name) as d:
            exe = Path(d) / "Aggiornamenti.exe"
            exe.write_bytes(b"old-executable")
            self._run(exe, b"MZ" + b"x" * (2 << 20), "0" * 64)
            self.assertEqual(exe.read_bytes(), b"old-executable")
            self.assertEqual(s.state["self"]["status"], "error")

    def test_failed_swap_restores_current_exe(self):
        with tempfile.TemporaryDirectory(dir=SANDBOX.name) as d:
            exe = Path(d) / "Aggiornamenti.exe"
            exe.write_bytes(b"old-executable")
            payload = b"MZ" + b"x" * (2 << 20)
            real = os.replace

            def replace(src, dst):
                if str(src).endswith(".new"):
                    raise PermissionError("replacement denied")
                return real(src, dst)
            self._run(exe, payload, hashlib.sha256(payload).hexdigest(), replace)
            self.assertEqual(exe.read_bytes(), b"old-executable")
            self.assertEqual(s.state["self"]["status"], "error")

    def test_release_without_assets_is_not_offered(self):
        s.state["self"].update(latest="9.9.9", assets={})
        with patch.object(s, "install_method", return_value="exe"):
            self.assertIsNone(s.self_update_available())


class Api(Base):
    def test_disabling_task_reports_failure(self):
        with patch.object(s, "powershell", return_value=(1, "Access denied")), patch.object(s, "refresh_task"):
            s._task.update(exists=True, login=True, read=True)
            self.assertFalse(s.set_login(False, keep_task=False))

    def test_quit_during_update_waits(self):
        s.state["running"] = True
        with patch.object(s.threading, "Timer") as timer:
            self.assertFalse(s.request_quit())
        timer.assert_not_called()
        self.assertTrue(s.state["quit_after"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
