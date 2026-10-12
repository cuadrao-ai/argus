"""Static guards for the iPhone on-device guest book ("Probar sin cuenta").

They protect three promises without running the app: the Release build keeps the
door closed, the package stays dependency free, and the guest folder never reaches
the network or a server-bound model.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "ios/ArgusFoundation/Guest/CuadraoGuestGate.swift"
GUEST = ROOT / "ios/ArgusFoundation/Guest"
PACKAGE = ROOT / "ios/Packages/CuadraoBook"

# The server-bound pieces the plan names as off limits, plus anything that opens a connection.
FORBIDDEN_IN_GUEST_CODE = (
    "URLSession",
    "URLRequest",
    "NWConnection",
    "WebSocket",
    "import ArgusSession",
    "SessionController",
    "FinancialWriteJournal",
    "FinancialHome",
    "FinancialPlanProjection",
    "AccountDraft",
    "commonISOCurrencyCodes",
    "ConnectedAccountOrder",
    "CanvasMoney.format",
    "America/Santo_Domingo",
)


def test_release_build_keeps_the_guest_door_closed():
    text = GATE.read_text()
    release = text.split("#else", 1)[1].split("#endif", 1)[0]
    assert re.search(r"static let guestBook\s*=\s*false\b", release), "Release guestBook must be the literal false"
    debug = text.split("#if DEBUG", 1)[1].split("#else", 1)[0]
    assert '"--cuadrao-guest-book"' in debug
    assert re.search(r"static let guestClaim\s*=\s*false\b", text), "claiming a book into an account stays off"


def test_package_declares_no_dependencies():
    manifest = (PACKAGE / "Package.swift").read_text()
    assert ".package(" not in manifest
    for match in re.finditer(r"dependencies:\s*(\[[^\]]*\])", manifest):
        assert match.group(1) == '["CuadraoBook"]', "only the test target may depend on the book itself"


def test_package_sources_import_foundation_only():
    for source in (PACKAGE / "Sources/CuadraoBook").glob("*.swift"):
        imports = [line for line in source.read_text().splitlines() if line.startswith("import ")]
        assert all(line == "import Foundation" for line in imports), (source.name, imports)


def test_guest_code_has_no_network_or_server_bound_model():
    offenders = []
    for source in GUEST.rglob("*.swift"):
        text = source.read_text()
        # A name must stand alone: the book's own BookAccountDraft is not the server-bound AccountDraft.
        offenders += [(source.name, token) for token in FORBIDDEN_IN_GUEST_CODE
                      if re.search(r"(?<![A-Za-z])" + re.escape(token), text)]
    assert not offenders, offenders


def test_guest_copy_has_no_em_dash():
    for source in [*GUEST.rglob("*.swift")]:
        assert "—" not in source.read_text(), source.name
