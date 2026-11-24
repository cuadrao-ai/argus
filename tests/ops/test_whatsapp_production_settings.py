from pathlib import Path

import yaml


def test_production_api_declares_credentials_and_keeps_whatsapp_off() -> None:
    services = yaml.safe_load(
        (Path(__file__).resolve().parents[2] / "render.yaml").read_text()
    )["services"]
    api = next(service for service in services if service["name"] == "cuadrao-api")
    entries = {entry["key"]: entry for entry in api["envVars"]}
    for suffix in (
        "VERIFY_TOKEN",
        "APP_SECRET",
        "ACCESS_TOKEN",
        "SENDER_KEY",
        "NUMBER_ID",
        "DISPLAY_PHONE_NUMBER",
    ):
        key = f"CUADRAO_WHATSAPP_{suffix}"
        assert entries[key] == {"key": key, "sync": False}
    for suffix in ("INTAKE_ENABLED", "OUTBOUND_ENABLED"):
        key = f"CUADRAO_WHATSAPP_{suffix}"
        assert entries[key] == {"key": key, "value": "false"}
