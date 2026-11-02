"""v1.37.2: "Playing Capri" on your Discord profile (Rich Presence through the Discord app's local socket),
tested against a stand-in Discord that speaks the same protocol."""

from __future__ import annotations

import json
import os
import socket
import struct
import sys
import tempfile
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pytest  # noqa: E402

from capri.integrations import discord_presence as dp  # noqa: E402

pytestmark = pytest.mark.skipif(not hasattr(socket, "AF_UNIX"), reason="Unix sockets")


class FakeDiscord:
    """Discord's local RPC: handshake -> READY, SET_ACTIVITY -> echo, CLOSE."""

    def __init__(self, refuse: bool = False) -> None:
        self.dir = tempfile.mkdtemp(prefix="dc")
        self.path = os.path.join(self.dir, "discord-ipc-0")
        self.server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.server.bind(self.path)
        self.server.listen(5)
        self.refuse = refuse
        self.got: list[tuple[int, dict]] = []
        self.connections = 0
        threading.Thread(target=self._serve, daemon=True).start()

    def _read(self, conn, n):
        buf = b""
        while len(buf) < n:
            chunk = conn.recv(n - len(buf))
            if not chunk:
                raise OSError("closed")
            buf += chunk
        return buf

    def _send(self, conn, op, payload):
        data = json.dumps(payload).encode()
        conn.sendall(struct.pack("<II", op, len(data)) + data)

    def _serve(self):
        while True:
            try:
                conn, _ = self.server.accept()
            except OSError:
                return
            self.connections += 1
            threading.Thread(target=self._client, args=(conn,), daemon=True).start()

    def _client(self, conn):
        try:
            while True:
                op, length = struct.unpack("<II", self._read(conn, 8))
                payload = json.loads(self._read(conn, length) or b"{}")
                self.got.append((op, payload))
                if op == 0:
                    if self.refuse:
                        self._send(conn, 2, {"code": 4000, "message": "Invalid Client ID"})
                        return
                    self._send(conn, 1, {"cmd": "DISPATCH", "evt": "READY", "data": {"user": {"username": "zed_the_tester"}}})
                elif op == 1:
                    self._send(conn, 1, {"cmd": payload["cmd"], "data": payload["args"].get("activity"),
                                         "nonce": payload.get("nonce")})
                elif op == 2:
                    return
        except OSError:
            return
        finally:
            conn.close()

    def activities(self):
        return [p["args"]["activity"] for op, p in self.got if op == 1 and p.get("cmd") == "SET_ACTIVITY"]

    def stop(self):
        self.server.close()


def presence(fake, enabled=lambda: True):
    clock = [100.0]
    p = dp.DiscordPresence("1234567890", enabled=enabled, connect=lambda: dp.connect_to_discord([fake.path]),
                           clock=lambda: clock[0], now=lambda: 1_700_000_000)
    return p, clock


def settle(check, seconds=2.0):
    end = time.time() + seconds
    while time.time() < end:
        if check():
            return True
        time.sleep(0.02)
    return check()


def test_she_shows_up_as_playing_capri():
    fake = FakeDiscord()
    try:
        p, clock = presence(fake)
        p.step()
        assert settle(lambda: len(fake.activities()) == 1)
        hello = fake.got[0]
        assert hello == (0, {"v": 1, "client_id": "1234567890"})
        act = fake.activities()[0]
        assert act["details"] == "Plugged in" and "state" not in act and act["timestamps"] == {"start": 1_700_000_000}
        assert act["assets"]["large_image"] == dp.ART + "capri.gif" and act["buttons"][0]["url"] == dp.PAGE
        assert "zed_the_tester" not in json.dumps(act)                       # nothing about you
        p.step()                                                      # nothing changed: nothing sent
        assert len(fake.activities()) == 1
        clock[0] += 10
        p.set_state("drone")
        p.step()
        assert settle(lambda: len(fake.activities()) == 2) and fake.activities()[1]["state"] == "Drone mode"
    finally:
        fake.stop()


def test_turning_it_off_clears_it():
    fake = FakeDiscord()
    on = [True]
    try:
        p, clock = presence(fake, enabled=lambda: on[0])
        p.step()
        on[0] = False
        clock[0] += 10
        p.step()
        assert settle(lambda: fake.activities()[-1:] == [None]) and p.conn is None
        p.step()                                                      # stays off: doesn't reconnect
        assert fake.connections == 1
    finally:
        fake.stop()


def test_no_discord_is_fine():
    p = dp.DiscordPresence("1", connect=lambda: None, clock=lambda: 0.0)
    p.step()                                                          # Discord isn't running: nothing happens
    assert p.conn is None and p._next_try == dp.RETRY_SECONDS


def test_a_wrong_app_id_is_reported_not_crashed():
    fake = FakeDiscord(refuse=True)
    try:
        p, _clock = presence(fake)
        with pytest.raises(OSError) as caught:
            p.step()
        assert "Invalid Client ID" in str(caught.value)
    finally:
        fake.stop()


def test_closing_capri_clears_it():
    fake = FakeDiscord()
    try:
        p, _clock = presence(fake)
        p.step()
        p.close()
        assert settle(lambda: fake.activities()[-1:] == [None] and fake.got[-1][0] == 2)
    finally:
        fake.stop()


def test_background_thread_reconnects_after_discord_restarts():
    fake = FakeDiscord()
    p = dp.DiscordPresence("42", connect=lambda: dp.connect_to_discord([fake.path]))
    try:
        p.start()
        assert settle(lambda: len(fake.activities()) == 1, 5)
    finally:
        p.close()
        fake.stop()


def test_linux_sockets_include_flatpak_and_snap():
    paths = dp.socket_paths({"XDG_RUNTIME_DIR": "/run/user/1000"})
    assert "/run/user/1000/discord-ipc-0" in paths
    assert "/run/user/1000/app/com.discordapp.Discord/discord-ipc-0" in paths
    assert "/run/user/1000/snap.discord/discord-ipc-0" in paths


def test_without_an_app_id_it_stays_off():
    p = dp.DiscordPresence("", connect=lambda: pytest.fail("shouldn't connect"))
    p.start()
    assert not p.available and p._thread is None


def test_her_buttons():
    act = dp.activity("desktop", 1, "https://discord.gg/abc123")
    assert [b["label"] for b in act["buttons"]] == ["Get Capri", "Join her Discord"]
    assert act["buttons"][1]["url"] == "https://discord.gg/abc123"
    assert [b["label"] for b in dp.activity("desktop", 1, "")["buttons"]] == ["Get Capri"]       # no server yet
    assert [b["label"] for b in dp.activity("desktop", 1, "https://evil.example")["buttons"]] == ["Get Capri"]
    assert all(len(b["label"]) <= 32 for b in act["buttons"])                                   # Discord's limit
