"""Private owner Shell control. Never reads settings, tokens or provider APIs.

After separate exact-SHA rollout approval, run status in the service Shell.
Create a mode-600 JSON arm file from that status and the approved synthetic
scope. Include a freshly operator-verified one-instance/one-worker assertion,
deployment ID and topology_observed_at Unix time. Arm once. A refusal or crash
requires a new decision; never retry the experiment or send another PDF.
The switch alone never arms. With it on, ordinary intake returns retryable 503.
Restoring ordinary intake requires an approved switch-off and process restart.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import stat
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("status", "arm"))
    parser.add_argument(
        "--scope", type=Path, help="private mode-600 arm JSON, required for arm"
    )
    args = parser.parse_args()
    directory = Path(f"/tmp/cuadrao-whatsapp-diagnostic-{os.geteuid()}")
    try:
        info = directory.lstat()
        if (
            not stat.S_ISDIR(info.st_mode)
            or info.st_uid != os.geteuid()
            or stat.S_IMODE(info.st_mode) != 0o700
        ):
            raise ValueError
        command = {"action": args.action}
        if args.action == "arm":
            fd = os.open(args.scope, os.O_RDONLY | os.O_NOFOLLOW)
            with os.fdopen(fd, "rb") as source:
                found = os.fstat(source.fileno())
                if (
                    not stat.S_ISREG(found.st_mode)
                    or found.st_uid != os.geteuid()
                    or stat.S_IMODE(found.st_mode) != 0o600
                    or found.st_nlink != 1
                ):
                    raise ValueError
                command["scope"] = json.loads(source.read(8193))
        encoded = json.dumps(command).encode() + b"\n"
        if len(encoded) > 8192:
            raise ValueError
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.settimeout(5)
            connection.connect(str(directory / "control.sock"))
            connection.sendall(encoded)
            response = bytearray()
            while not response.endswith(b"\n") and len(response) < 8192:
                chunk = connection.recv(8192 - len(response))
                if not chunk:
                    break
                response.extend(chunk)
        data = json.loads(response)
        # Only the server's nonsecret readiness or accepted boolean is emitted.
        sys.stdout.write(json.dumps(data) + "\n")
        return 0 if args.action == "status" or data == {"accepted": True} else 1
    except Exception:
        sys.stderr.write(
            "Private diagnostic control refused or unavailable. Stop; do not send.\n"
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
