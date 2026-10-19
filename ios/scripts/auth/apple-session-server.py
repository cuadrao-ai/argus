import base64
import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from uuid import uuid4

OWNER = "3a25203a-6cc2-4d2c-9d07-7840110dbb78"
USER = {
    "id": OWNER,
    "aud": "authenticated",
    "role": "authenticated",
    "email": "synthetic@example.test",
    "is_anonymous": False,
    "app_metadata": {},
    "user_metadata": {},
    "created_at": "2026-10-05T00:00:00Z",
    "updated_at": "2026-10-05T00:00:00Z",
}


def session():
    expires = int(time.time()) + 3600
    payload = (
        base64.urlsafe_b64encode(json.dumps({"sub": OWNER, "exp": expires}).encode())
        .decode()
        .rstrip("=")
    )
    return {
        "access_token": f"header.{payload}.signature",
        "refresh_token": str(uuid4()),
        "token_type": "bearer",
        "expires_in": 3600,
        "expires_at": expires,
        "user": USER,
    }


class Handler(BaseHTTPRequestHandler):
    linked = True
    signup_requests = []

    def log_message(self, *_):
        pass

    def do_GET(self):
        self.respond()

    def do_POST(self):
        data = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        if self.path == "/api/v1/auth/signup":
            Handler.signup_requests.append(json.loads(data))
        self.respond()

    def respond(self):
        path = self.path.split("?")[0]
        status = 200
        if path.startswith("/synthetic/identity-"):
            Handler.linked = path.endswith("identity-present")
            body = {}
        elif path == "/synthetic/age-signup-reset":
            Handler.signup_requests = []
            body = {}
        elif path == "/synthetic/age-signup":
            body = Handler.signup_requests
        elif path == "/api/v1/auth/signup":
            body = {"session": None}
        elif path == "/api/v1/auth/login":
            body = {"session": session()}
        elif path == "/auth/v1/token":
            body = session()
        elif path == "/auth/v1/user":
            body = USER
        elif path == "/auth/v1/logout":
            status, body = 204, {}
        elif path == "/api/v1/me":
            body = {
                "user": {
                    "id": OWNER,
                    "email": USER["email"],
                    "display_name": "Synthetic owner",
                    "language": "en",
                },
                "apple_identity": {"subject": "synthetic-canonical-subject"}
                if Handler.linked
                else None,
            }
        elif path == "/api/v1/auth/apple/authorization-code":
            status, body = 503, {"code": "apple_sign_in_unavailable"}
        else:
            status, body = 404, {"detail": "Not Found"}
        encoded = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", 59920), Handler).serve_forever()
