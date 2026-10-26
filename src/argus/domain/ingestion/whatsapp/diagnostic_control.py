"""Service-user Unix control and one private evidence file. No network on startup."""

from __future__ import annotations

import asyncio
import ctypes
import fcntl
import json
import os
import socket
import stat
import struct
from pathlib import Path

from argus.domain.ingestion.whatsapp.diagnostic_once import DiagnosticOnce

MAX_RECORD = 65536


def control_directory() -> Path:
    return Path(f"/tmp/cuadrao-whatsapp-diagnostic-{os.geteuid()}")


def _owned(path: Path, mode: int, kind: int) -> bool:
    found = path.lstat()
    return (
        found.st_uid == os.geteuid()
        and stat.S_IMODE(found.st_mode) == mode
        and stat.S_IFMT(found.st_mode) == kind
        and (kind == stat.S_IFDIR or found.st_nlink == 1)
    )


def _peer_uid(writer: asyncio.StreamWriter) -> int:
    peer = writer.get_extra_info("socket")
    if hasattr(socket, "SO_PEERCRED"):
        return struct.unpack(
            "3i", peer.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12)
        )[1]
    uid, gid = ctypes.c_uint(), ctypes.c_uint()
    getpeereid = ctypes.CDLL(None, use_errno=True).getpeereid
    if getpeereid(peer.fileno(), ctypes.byref(uid), ctypes.byref(gid)) != 0:
        raise ValueError
    return uid.value


class DiagnosticControl:
    def __init__(self, observer: DiagnosticOnce, directory: Path | None = None) -> None:
        self.observer, self.directory = observer, directory or control_directory()
        self.path = self.directory / "control.sock"
        self.result_path = self.directory / f"result-{observer.nonce}.json"
        self.server: asyncio.AbstractServer | None = None
        self.lease: int | None = None
        self.timer: asyncio.TimerHandle | None = None
        self.socket_inode: int | None = None
        self.written = False
        observer.control = self

    async def start(self) -> bool:
        try:
            try:
                self.directory.mkdir(mode=0o700)
            except FileExistsError:
                pass
            if _owned(self.directory, 0o2700, stat.S_IFDIR):
                fd = os.open(self.directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
                try:
                    found = os.fstat(fd)
                    if (
                        found.st_uid != os.geteuid()
                        or stat.S_IMODE(found.st_mode) != 0o2700
                    ):
                        raise ValueError
                    os.fchmod(fd, 0o700)
                finally:
                    os.close(fd)
            if not _owned(self.directory, 0o700, stat.S_IFDIR):
                raise ValueError
            lock_path = self.directory / "owner.lock"
            try:
                self.lease = os.open(
                    lock_path, os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_RDWR, 0o600
                )
                os.write(self.lease, b"cuadrao-diagnostic-v1\n")
            except FileExistsError:
                if not _owned(lock_path, 0o600, stat.S_IFREG):
                    raise ValueError from None
                self.lease = os.open(lock_path, os.O_NOFOLLOW | os.O_RDWR)
                if os.read(self.lease, 64) != b"cuadrao-diagnostic-v1\n":
                    raise ValueError from None
            fcntl.flock(self.lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
            # Never delete a stale or foreign socket on startup.
            if self.path.exists() or self.path.is_symlink():
                raise ValueError
            self.server = await asyncio.start_unix_server(
                self._handle, str(self.path), limit=8192
            )
            os.chmod(self.path, 0o600)
            self.socket_inode = self.path.lstat().st_ino
            return True
        except Exception:
            self.observer.state = "sealed"
            self.close()
            return False

    def exclusive(self) -> bool:
        return (
            self.lease is not None
            and self.server is not None
            and self.server.is_serving()
        )

    def schedule_expiry(self, delay: float) -> None:
        self.timer = asyncio.get_running_loop().call_later(
            delay, self.observer.seal, "expired"
        )

    async def _handle(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        response: dict = {"accepted": False}
        try:
            if _peer_uid(writer) != os.geteuid():
                raise ValueError
            raw = await asyncio.wait_for(reader.readline(), timeout=3)
            if len(raw) > 8192 or not raw.endswith(b"\n"):
                raise ValueError
            command = json.loads(raw)
            if command == {"action": "status"}:
                response = self.observer.status()
            elif set(command) == {"action", "scope"} and command["action"] == "arm":
                response = {"accepted": self.observer.arm(command["scope"])}
        except Exception:
            pass
        try:
            writer.write(json.dumps(response).encode() + b"\n")
            await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()

    def finish(self, result: dict) -> None:
        if not self.written:
            self.written = True
            try:
                data = json.dumps(result, separators=(",", ":")).encode()
                if len(data) > MAX_RECORD:
                    raise ValueError
                fd = os.open(
                    self.result_path,
                    os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_WRONLY,
                    0o600,
                )
                with os.fdopen(fd, "wb") as output:
                    output.write(data)
                    output.flush()
                    os.fsync(output.fileno())
            except Exception:
                # The slot stays sealed even if private storage is unavailable.
                self.observer.result = {"outcome": "private_record_unavailable"}
        self.close_socket()

    def close_socket(self) -> None:
        if self.timer is not None:
            self.timer.cancel()
            self.timer = None
        if self.server is not None:
            self.server.close()
        try:
            if (
                self.socket_inode is not None
                and self.path.lstat().st_ino == self.socket_inode
            ):
                self.path.unlink()
        except FileNotFoundError:
            pass

    def close(self) -> None:
        self.close_socket()
        if self.lease is not None:
            os.close(self.lease)
            self.lease = None
