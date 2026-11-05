"""Inject isolated local financial transport failures for native recovery checks."""

from __future__ import annotations

import argparse
import http.client
import json
import socket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Lock
from time import sleep
from urllib.parse import urlsplit


class Fault:
    def __init__(self) -> None:
        self.lock = Lock()
        self.armed = False
        self.dropped = 0
        self.read_fault: tuple[str, int, int] | None = None
        self.read_consumed = 0

    def arm_read(self, path_prefix: str, status: int, delay_ms: int = 0) -> None:
        if (
            not (
                path_prefix.startswith("/api/v1/financial-")
                or path_prefix == "/api/v1/households"
                or path_prefix.startswith("/api/v1/households/")
            )
            or status not in {0, 404, 503}
            or not 0 <= delay_ms <= 10_000
        ):
            raise ValueError("Only bounded local financial read faults are supported.")
        with self.lock:
            self.read_fault = path_prefix, status, delay_ms

    def consume_read(self, method: str, path: str) -> tuple[int, int] | None:
        with self.lock:
            if (
                method != "GET"
                or self.read_fault is None
                or not path.startswith(self.read_fault[0])
            ):
                return None
            _, status, delay_ms = self.read_fault
            self.read_fault = None
            self.read_consumed += 1
            return status, delay_ms

    def arm(self) -> None:
        with self.lock:
            self.armed = True

    def consume(self, method: str, path: str, status: int) -> bool:
        eligible = (
            (
                method in {"POST", "PATCH", "PUT"}
                or (
                    method == "DELETE"
                    and path.startswith("/api/v1/households/")
                    and "/account-grants/" in path
                )
            )
            and (
                path == "/api/v1/financial-activities"
                or path.startswith("/api/v1/financial-activities/")
                or path.startswith("/api/v1/financial-plan/")
                or path == "/api/v1/financial-accounts"
                or path.startswith("/api/v1/financial-accounts/")
                or path == "/api/v1/households"
                or path.startswith("/api/v1/households/")
                or path == "/api/v1/household-invitations/accept"
            )
            and not path.endswith("/preview")
            and 200 <= status < 300
        )
        with self.lock:
            if not self.armed or not eligible:
                return False
            self.armed = False
            self.dropped += 1
            return True


def handler(upstream_port: int, fault: Fault) -> type[BaseHTTPRequestHandler]:
    class Proxy(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            pass

        def json_response(self, status: int, payload: dict[str, object]) -> None:
            body = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def forward(self) -> None:
            if self.path == "/__read_fault":
                if self.command == "POST":
                    try:
                        size = int(self.headers.get("Content-Length", 0))
                        if not 0 < size <= 1024:
                            raise ValueError("Invalid fault payload size")
                        body = json.loads(self.rfile.read(size))
                        fault.arm_read(
                            body["path_prefix"], body["status"], body.get("delay_ms", 0)
                        )
                    except (ValueError, KeyError, TypeError, AttributeError):
                        self.json_response(400, {"detail": "Invalid read fault"})
                        return
                with fault.lock:
                    payload = {
                        "armed": fault.read_fault is not None,
                        "consumed": fault.read_consumed,
                    }
                self.json_response(200, payload)
                return
            if self.path == "/__fault":
                if self.command == "POST":
                    fault.arm()
                with fault.lock:
                    payload = json.dumps(
                        {"armed": fault.armed, "dropped": fault.dropped}
                    ).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
                return
            if not self.path.startswith("/api/v1/"):
                self.send_error(404)
                return
            read_fault = fault.consume_read(self.command, urlsplit(self.path).path)
            if read_fault:
                status, delay_ms = read_fault
                sleep(delay_ms / 1000)
                if status:
                    self.json_response(status, {"detail": {"code": "unavailable"}})
                    return
            content = self.rfile.read(int(self.headers.get("Content-Length", 0)))
            excluded = {"host", "connection", "transfer-encoding", "content-length"}
            headers = {k: v for k, v in self.headers.items() if k.lower() not in excluded}
            upstream = http.client.HTTPConnection("127.0.0.1", upstream_port, timeout=45)
            try:
                upstream.request(self.command, self.path, content, headers)
                response = upstream.getresponse()
                body = response.read()
                if fault.consume(self.command, urlsplit(self.path).path, response.status):
                    self.close_connection = True
                    self.connection.shutdown(socket.SHUT_RDWR)
                    self.connection.close()
                    return
                self.send_response(response.status)
                for key, value in response.getheaders():
                    if key.lower() not in excluded:
                        self.send_header(key, value)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except (ConnectionError, TimeoutError):
                self.close_connection = True
            finally:
                upstream.close()

        do_GET = forward
        do_POST = forward
        do_PATCH = forward
        do_PUT = forward
        do_DELETE = forward

    return Proxy


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--listen-port", type=int, default=58512)
    parser.add_argument("--upstream-port", type=int, default=58500)
    args = parser.parse_args()
    if args.listen_port == args.upstream_port:
        parser.error("The proxy and API need different ports.")
    ThreadingHTTPServer(
        ("127.0.0.1", args.listen_port), handler(args.upstream_port, Fault())
    ).serve_forever()
