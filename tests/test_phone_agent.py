from pathlib import Path
import socket
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import phone_agent as pa


class ConfigTests(unittest.TestCase):
    def test_unconfigured_install(self):
        self.assertIsNone(pa.Config.parse({}).adb_port)
        self.assertEqual(pa.PORTS, (3773, 1455))

    def test_reject_invalid_ports_hosts_and_unknown_settings(self):
        for value in (True, 0, -1, 65536, "12345", 3773, 1455):
            with self.subTest(port=value), self.assertRaises(ValueError):
                pa.Config.parse({"adb_port": value})
        for value in ([], {"extra": 1}, {"adb_host": "-bad host"}):
            with self.subTest(data=value), self.assertRaises(ValueError):
                pa.Config.parse(value)

    def test_gateway_failure_requires_explicit_host(self):
        with patch.object(pa, "run", return_value=(0, "default dev wlan0")):
            with self.assertRaisesRegex(RuntimeError, "--host"):
                pa.endpoint(pa.Config(adb_port=12345))
        self.assertEqual(pa.endpoint(pa.Config("::1", 12345)), "[::1]:12345")

    def test_saved_configuration_roundtrip(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "config.json"
            config = pa.Config("192.0.2.1", 12345)
            pa.save_config(path, config)
            self.assertEqual(pa.read_config(path), config)


class ProtocolTests(unittest.TestCase):
    def server(self, reject_service=False):
        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        commands, errors = [], []
        port = listener.getsockname()[1]

        def serve():
            try:
                with listener, listener.accept()[0] as connection:
                    connection.settimeout(3)
                    for index in range(2):
                        count = int(pa.receive_exact(connection, 4), 16)
                        commands.append(pa.receive_exact(connection, count).decode())
                        # Fragment frames to exercise actual socket reads.
                        for byte in b"OKAY":
                            connection.sendall(bytes([byte]))
                        if index == 1:
                            connection.sendall(b"FAIL0004busy" if reject_service else b"OKAY00043773")
            except Exception as error:
                errors.append(error)

        thread = threading.Thread(target=serve, daemon=True)
        thread.start()
        return port, commands, errors, thread

    def test_loopback_socket_and_both_status_frames(self):
        port, commands, errors, thread = self.server()
        pa.reverse_loopback("device-under-test", 3773, port)
        thread.join(4)
        self.assertFalse(thread.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(commands, ["host:transport:device-under-test", "reverse:forward:tcp:localhost:3773;tcp:3773"])

    def test_transport_okay_does_not_hide_listener_failure(self):
        port, _, errors, thread = self.server(reject_service=True)
        with self.assertRaisesRegex(OSError, "busy"):
            pa.reverse_loopback("device-under-test", 3773, port)
        thread.join(4)
        self.assertFalse(thread.is_alive())
        self.assertEqual(errors, [])

    def test_truncated_status_is_an_error(self):
        first, second = socket.socketpair()
        with first, second:
            second.sendall(b"OK")
            second.shutdown(socket.SHUT_WR)
            with self.assertRaises(OSError):
                pa.adb_status(first)


class MappingTests(unittest.TestCase):
    config = pa.Config("192.0.2.1", 12345)

    def test_startup_replaces_old_listeners_then_keeps_healthy_mappings(self):
        def connected(*arguments, device=None):
            return (0, "device") if arguments == ("get-state",) else (0, "owner tcp:3773 tcp:3773\nowner tcp:1455 tcp:1455")
        link = pa.Link()
        with patch.object(pa, "adb", side_effect=connected), patch.object(pa, "reverse_loopback") as reverse:
            self.assertIn("ready", link.cycle(self.config))
            self.assertEqual(reverse.call_count, 2)
            link.cycle(self.config)
            self.assertEqual(reverse.call_count, 2)

    def test_disconnect_forces_repair_after_reconnect(self):
        link = pa.Link()
        link.device = pa.endpoint(self.config)
        with patch.object(pa, "adb", return_value=(1, "offline")):
            self.assertIn("unavailable", link.cycle(self.config))
        self.assertIsNone(link.device)
        with patch.object(pa, "adb", side_effect=[(0, "device"), (0, "")]), patch.object(pa, "reverse_loopback") as reverse:
            self.assertIn("ready", link.cycle(self.config))
            self.assertEqual(reverse.call_count, 2)

    def test_failed_listener_does_not_report_ready(self):
        with patch.object(pa, "adb", side_effect=[(0, "device"), (0, "")]), \
             patch.object(pa, "reverse_loopback", side_effect=OSError("busy")):
            link = pa.Link()
            with self.assertRaises(OSError):
                link.cycle(self.config)
            self.assertIsNone(link.device)

    def test_missing_listener_is_restored_without_replacing_other_port(self):
        link = pa.Link()
        link.device = pa.endpoint(self.config)
        with patch.object(pa, "adb", side_effect=[(0, "device"), (0, "owner tcp:3773 tcp:3773")]), \
             patch.object(pa, "reverse_loopback") as reverse:
            link.cycle(self.config)
        reverse.assert_called_once_with(link.device, 1455)

    def test_cleanup_leaves_unrelated_mappings(self):
        calls = []
        def fake_adb(*arguments, device=None):
            calls.append(arguments)
            return 0, "owner tcp:3773 tcp:3773\nowner tcp:9999 tcp:9999\nowner tcp:1455 tcp:9999"
        with patch.object(pa, "adb", side_effect=fake_adb):
            pa.remove_mappings("device-under-test")
        self.assertEqual(calls, [("reverse", "--list"), ("reverse", "--remove", "tcp:3773")])


class CommandTests(unittest.TestCase):
    def test_pair_saves_host_only_after_success_and_keeps_connection_port(self):
        with tempfile.TemporaryDirectory() as root, patch.object(Path, "home", return_value=Path(root)):
            path = Path(root) / ".config/android-local-agent/config.json"
            original = pa.Config("192.0.2.1", 54321)
            pa.save_config(path, original)
            with patch.object(pa.subprocess, "call", return_value=1):
                self.assertEqual(pa.main(["pair", "12345", "--host", "192.0.2.2"]), 1)
            self.assertEqual(pa.read_config(path), original)
            with patch.object(pa.subprocess, "call", return_value=0) as pair:
                self.assertEqual(pa.main(["pair", "12345", "--host", "192.0.2.2"]), 0)
            self.assertEqual(pa.read_config(path), pa.Config("192.0.2.2", 54321))
            self.assertEqual(pair.call_args.args[0][-2:], ["pair", "192.0.2.2:12345"])

    def test_connect_persists_new_port_and_restarts_daemon(self):
        with tempfile.TemporaryDirectory() as root, patch.object(Path, "home", return_value=Path(root)):
            path = Path(root) / ".config/android-local-agent/config.json"
            pa.save_config(path, pa.Config("192.0.2.1"))
            with patch.object(pa.subprocess, "run") as restart:
                self.assertEqual(pa.main(["connect", "54321"]), 0)
            self.assertEqual(pa.read_config(path), pa.Config("192.0.2.1", 54321))
            restart.assert_called_once_with(["systemctl", "--user", "restart", pa.UNIT], check=True)

    def test_cleanup_refuses_to_race_running_daemon(self):
        with tempfile.TemporaryDirectory() as root, patch.object(Path, "home", return_value=Path(root)):
            pa.save_config(Path(root) / ".config/android-local-agent/config.json", pa.Config("192.0.2.1", 54321))
            with patch.object(pa, "run", return_value=(0, "active")), patch.object(pa, "remove_mappings") as remove:
                with self.assertRaisesRegex(RuntimeError, "Stop"):
                    pa.main(["cleanup"])
            remove.assert_not_called()


if __name__ == "__main__":
    unittest.main()
