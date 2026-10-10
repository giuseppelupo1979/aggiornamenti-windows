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
             patch.object(s, "installed_version", return_value="1.1"), \
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
             patch.object(s, "installed_version", return_value="1.1"), \
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
             patch.object(s, "automatic_block_reason", return_value=None), \
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


class Verification(Base):
    def update(self, code=0, version="1.1"):
        with patch.object(s, "running_in", return_value=[]), patch.object(s, "run_stream", return_value=(code, "installer output")), \
             patch.object(s, "installed_version", return_value=version), patch.object(s.time, "sleep"):
            s.update_one(ITEM)
        return s.state["jobs"][ITEM["id"]]["status"]

    def test_success_requires_observed_version(self):
        self.assertEqual(self.update(version="1.0"), "unverified")
        self.assertFalse(s.state["items"][0].get("updated", False))
        self.assertEqual(s.load_history()[-1]["observed"], "1.0")

    def test_missing_version_is_not_success(self):
        self.assertEqual(self.update(version=None), "unverified")

    def test_verified_version_saved_with_diagnostics(self):
        self.assertEqual(self.update(), "done")
        h = s.load_history()[-1]
        self.assertEqual((h["observed"], h["exit_code"], h["log"]), ("1.1", 0, "installer output"))

    def test_restart_codes_and_signed_hresult(self):
        for code in (3010, 1641, 0x8A150109, 0x8A150109 - 2**32, 0x8A15010B):
            with self.subTest(code=code):
                self.assertEqual(self.update(code), "restart")
        self.assertEqual(self.update(0x8A15010A), "restart_before")

    def test_failed_installer_never_becomes_success(self):
        self.assertEqual(self.update(1), "error")

    def test_versions_do_not_confuse_ten_and_one(self):
        self.assertFalse(s.version_matches("1.10", "1.1"))
        self.assertTrue(s.version_matches("1.1.0.0", "1.1"))
        self.assertFalse(s.version_matches("Unknown", "Unknown"))
        self.assertFalse(s.version_matches("1.1-beta", "1.1"))

    def test_version_query_requires_exact_package(self):
        output = table(f'{"Name":25}{"Id":25}{"Version":15}Source',
                       [f'{"App":25}{"Other.App":25}{"1.1":15}winget'])
        with patch.object(s, "run", return_value=(0, output)):
            self.assertIsNone(s.installed_version(ITEM))


class Snooze(Base):
    def test_timed_snooze_expires(self):
        with patch.object(s.time, "time", return_value=1000):
            s.snooze_item(ITEM, "day")
        self.assertIsNotNone(s.active_snooze(ITEM, now=87399))
        self.assertIsNone(s.active_snooze(ITEM, now=87400))

    def test_skip_only_requested_version(self):
        s.snooze_item(ITEM, "version")
        self.assertIsNotNone(s.active_snooze(ITEM))
        self.assertIsNone(s.active_snooze(dict(ITEM, latest="1.2")))
        self.assertEqual(s.visible_pending(), [])

    def test_resume_keeps_exclusion(self):
        s.save_excluded({ITEM["key"]: {"name": "App"}})
        s.snooze_item(ITEM, "week")
        s.snooze_item(ITEM, "resume")
        self.assertIsNone(s.active_snooze(ITEM))
        self.assertIn(ITEM["key"], s.load_excluded())

    def test_queue_cannot_install_snoozed_app(self):
        s.snooze_item(ITEM, "week")
        with patch.object(s, "update_one") as up, patch.object(s, "cleanup"):
            s.do_updates({ITEM["id"]})
        up.assert_not_called()


class Conditions(Base):
    def test_battery_or_unknown_power_blocks_automatic_updates(self):
        for ac, reason in ((False, "battery"), (None, "power_unknown")):
            with patch.object(s, "on_ac_power", return_value=ac):
                self.assertEqual(s.automatic_block_reason(), reason)

    def test_metered_and_unknown_network_block_automatic_updates(self):
        with patch.object(s, "on_ac_power", return_value=True):
            for cost in ("metered", "unknown", "offline", "unrestricted"):
                with patch.object(s, "network_cost", return_value=cost):
                    self.assertEqual(s.automatic_block_reason(), None if cost == "unrestricted" else cost)

    def test_opt_out_does_not_probe_system(self):
        with patch.object(s, "on_ac_power") as power, patch.object(s, "network_cost") as cost:
            self.assertIsNone(s.automatic_block_reason(dict(s.DEFAULT_SETTINGS, only_ac=False, avoid_metered=False)))
        power.assert_not_called()
        cost.assert_not_called()

    def test_blocked_auto_does_not_scan_or_consume_day(self):
        with patch.object(s, "automatic_block_reason", return_value="battery"), patch.object(s, "start_scan_sync") as scan:
            self.assertFalse(s.auto_update())
        scan.assert_not_called()
        self.assertEqual(s.state["auto_wait"], "battery")
        self.assertIsNone(s.load_settings()["last_auto_day"])

    def test_condition_rechecked_before_install(self):
        with patch.object(s, "automatic_block_reason", return_value="metered"), patch.object(s, "run_stream") as run:
            s.update_one(ITEM, "auto")
        run.assert_not_called()
        self.assertEqual(s.state["jobs"][ITEM["id"]]["status"], "deferred")

    def test_night_window_crosses_midnight(self):
        now = dt.datetime(2026, 10, 11, 1, 0)
        self.assertTrue(s.due("23:00", None, now, 5))
        self.assertFalse(s.due("23:00", "2026-10-10", now, 5))
        self.assertFalse(s.due("23:00", None, now.replace(hour=4), 5))

    def test_next_attempt_respects_window_and_completed_night(self):
        now = dt.datetime(2026, 10, 11, 6, 0)
        settings = dict(s.DEFAULT_SETTINGS, auto_update=True)
        self.assertEqual(s.next_auto_attempt(settings, now), (now + dt.timedelta(seconds=30)).timestamp())
        settings["last_auto_day"] = "2026-10-11"
        self.assertEqual(s.next_auto_attempt(settings, now), dt.datetime(2026, 10, 12, 3).timestamp())


class Diagnostics(Base):
    def test_export_redacts_personal_data_without_changing_versions(self):
        raw = r'C:\Users\Alice\file.log alice@example.org https://example.org/?token=secret token=abc'
        s.add_history({"name": "App", "from": "1.2.3.4", "log": raw})
        report = s.diagnostic_report()
        encoded = json.dumps(report)
        for private in ("Alice", "alice@example.org", "example.org", "secret", "abc"):
            self.assertNotIn(private, encoded)
        self.assertEqual(report["history"][0]["from"], "1.2.3.4")

    def test_settings_changes_preserve_snoozes(self):
        s.snooze_item(ITEM, "week")
        s.update_settings(lambda x: x.update(theme="light"))
        self.assertIsNotNone(s.active_snooze(ITEM))

    def test_defaults_are_not_mutated_by_snoozing(self):
        s.snooze_item(ITEM, "week")
        Path(s.SETTINGS_FILE).unlink()
        self.assertEqual(s.load_settings()["snoozed"], {})

    def test_redaction_covers_bearer_and_quoted_password(self):
        self.assertNotIn("private-token", s.redact("Authorization: Bearer private-token"))
        self.assertNotIn("private phrase", s.redact('password="a private phrase"'))


class NewApi(Base):
    def post(self, path, body):
        handler = object.__new__(s.Handler)
        raw = json.dumps(body).encode()
        handler.headers = {"Host": f"{s.HOST}:{s.PORT}", "Content-Length": str(len(raw))}
        handler.path = path
        handler.rfile = io.BytesIO(raw)
        replies = []
        handler.send = lambda code, payload: replies.append((code, payload))
        handler.snapshot = lambda: {"ok": True}
        handler.do_POST()
        return replies[-1]

    def test_settings_reject_invalid_types(self):
        for body in ({"only_ac": "false"}, {"avoid_metered": 0}, {"theme": "no"}, {"auto_time": "25:00"}):
            with self.subTest(body=body):
                self.assertEqual(self.post("/api/settings", body)[0], 400)

    def test_settings_saved_without_losing_snooze(self):
        s.snooze_item(ITEM, "version")
        self.assertEqual(self.post("/api/settings", {"only_ac": False, "theme": "dark"})[0], 200)
        self.assertFalse(s.load_settings()["only_ac"])
        self.assertEqual(s.load_settings()["theme"], "dark")
        self.assertIsNotNone(s.active_snooze(ITEM))

    def test_snooze_validated_and_persisted(self):
        self.assertEqual(self.post("/api/snooze", {"id": ITEM["id"], "choice": "week"})[0], 200)
        self.assertIsNotNone(s.active_snooze(ITEM))
        self.assertEqual(self.post("/api/snooze", {"id": ITEM["id"], "choice": "forever"})[0], 400)
        self.assertEqual(self.post("/api/snooze", {"id": "missing", "choice": "day"})[0], 404)

    def test_stale_selection_cannot_install_snoozed_app(self):
        s.snooze_item(ITEM, "day")
        self.assertEqual(self.post("/api/update", {"ids": [ITEM["id"]]})[0], 409)
        self.assertFalse(s.state["running"])

    def test_cannot_snooze_during_install(self):
        s.state["running"] = True
        self.assertEqual(self.post("/api/snooze", {"id": ITEM["id"], "choice": "day"})[0], 409)
        self.assertIsNone(s.active_snooze(ITEM))


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
