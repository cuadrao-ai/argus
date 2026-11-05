import http.client
import json
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from time import monotonic

import pytest
from financial_response_fault import Fault, handler


@contextmanager
def running(handler_type):
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler_type)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_port
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


@pytest.mark.parametrize(
    "method,path,status",
    [
        ("POST", "/api/v1/financial-activities/preview", 200),
        ("POST", "/api/v1/financial-activities", 409),
        ("GET", "/api/v1/financial-activities/entry", 200),
        ("POST", "/api/v1/auth/login", 200),
        ("POST", "/api/v1/financial-plan/occurrences/example/link/preview", 200),
        ("PUT", "/api/v1/financial-plan/selection", 409),
        ("GET", "/api/v1/financial-plan/expectations", 200),
        ("POST", "/api/v1/financial-accounts/example/asset-estimates/preview", 200),
        ("POST", "/api/v1/financial-accounts", 409),
        ("PUT", "/api/v1/financial-accounts/example/asset-details", 404),
        ("POST", "/api/v1/financial-accounts/example/asset-estimates", 503),
        ("GET", "/api/v1/financial-accounts/example", 200),
        ("POST", "/api/v1/financial-accounts-unrelated", 201),
        ("GET", "/api/v1/households", 200),
        ("POST", "/api/v1/households/example/activities/preview", 200),
        ("POST", "/api/v1/household-invitations/preview", 200),
        ("POST", "/api/v1/households", 409),
        ("DELETE", "/api/v1/households/example", 200),
        ("POST", "/api/v1/households-unrelated", 201),
        ("POST", "/api/v1/household-invitations/accept-other", 200),
    ],
)
def test_fault_ignores_reads_previews_and_failed_writes(method, path, status):
    fault = Fault()
    fault.arm()
    assert not fault.consume(method, path, status)
    assert fault.armed and fault.dropped == 0


@pytest.mark.parametrize(
    "method,path",
    [
        ("POST", "/api/v1/financial-activities"),
        ("POST", "/api/v1/households"),
        ("POST", "/api/v1/households/example/invitations"),
        ("POST", "/api/v1/household-invitations/accept"),
        ("PUT", "/api/v1/households/example/accounts/account/grants"),
        ("POST", "/api/v1/households/example/leave"),
        ("POST", "/api/v1/households/example/activities"),
        ("PATCH", "/api/v1/households/example/activities/activity"),
        ("DELETE", "/api/v1/households/example/account-grants/grant"),
        ("POST", "/api/v1/financial-accounts"),
        ("PATCH", "/api/v1/financial-accounts/example"),
        ("POST", "/api/v1/financial-accounts/example/asset-estimates"),
        ("PUT", "/api/v1/financial-accounts/example/asset-details"),
        ("POST", "/api/v1/financial-plan/expectations"),
        ("PATCH", "/api/v1/financial-plan/expectations/example"),
        ("PUT", "/api/v1/financial-plan/selection"),
        ("POST", "/api/v1/financial-plan/occurrences/example/fulfillment"),
        ("POST", "/api/v1/financial-plan/occurrences/example/link"),
    ],
)
def test_response_is_lost_only_after_upstream_accepts_the_write(method, path):
    accepted = []

    class API(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            pass

        def do_POST(self):
            accepted.append(self.rfile.read(int(self.headers["Content-Length"])))
            self.send_response(201)
            self.send_header("Content-Length", "2")
            self.end_headers()
            self.wfile.write(b"{}")

    API.do_PATCH = API.do_POST
    API.do_PUT = API.do_POST
    API.do_DELETE = API.do_POST
    fault = Fault()
    with running(API) as upstream, running(handler(upstream, fault)) as proxy:
        client = http.client.HTTPConnection("127.0.0.1", proxy, timeout=3)
        client.request("POST", "/__fault")
        assert client.getresponse().read() == b'{"armed": true, "dropped": 0}'
        client.request(method, path, b'{"amount":"10"}')
        with pytest.raises(http.client.RemoteDisconnected):
            client.getresponse()
        assert accepted == [b'{"amount":"10"}']
        client.request(method, path, b'{"amount":"10"}')
        response = client.getresponse()
        assert response.status == 201 and response.read() == b"{}"
        assert fault.dropped == 1 and not fault.armed
        client.close()


@pytest.mark.parametrize("status", [0, 404, 503])
def test_read_fault_is_once_and_never_intercepts_a_write(status):
    fault = Fault()
    fault.arm_read("/api/v1/financial-search", status, 20)
    assert fault.consume_read("POST", "/api/v1/financial-search") is None
    assert fault.consume_read("GET", "/api/v1/auth/session") is None
    assert fault.consume_read("GET", "/api/v1/financial-search") == (status, 20)
    assert fault.consume_read("GET", "/api/v1/financial-search") is None
    assert fault.read_consumed == 1


@pytest.mark.parametrize("status", [0, 404, 503])
def test_read_failure_retries_against_the_actual_upstream(status):
    reads = []

    class API(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            pass

        def do_GET(self):
            reads.append(self.path)
            body = b'{"items":[{"id":"owned-record"}]}'
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    with running(API) as upstream, running(handler(upstream, Fault())) as proxy:
        client = http.client.HTTPConnection("127.0.0.1", proxy, timeout=3)
        body = json.dumps(
            {"path_prefix": "/api/v1/financial-search", "status": status, "delay_ms": 25}
        )
        client.request("POST", "/__read_fault", body)
        response = client.getresponse()
        assert response.status == 200
        assert json.loads(response.read())["armed"]
        started = monotonic()
        client.request("GET", "/api/v1/financial-search?q=owned")
        response = client.getresponse()
        assert response.status == (status or 200)
        response.read()
        assert monotonic() - started >= 0.025
        assert reads == ([] if status else ["/api/v1/financial-search?q=owned"])
        client.request("GET", "/api/v1/financial-search?q=owned")
        response = client.getresponse()
        assert response.status == 200
        assert json.loads(response.read())["items"][0]["id"] == "owned-record"
        assert reads == ["/api/v1/financial-search?q=owned"] * (1 if status else 2)
        client.close()
