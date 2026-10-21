import argparse
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx

SPEC = importlib.util.spec_from_file_location(
    "readback", Path(__file__).with_name("consumer-money-readback.py")
)
readback = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(readback)


def row(
    code="DOP", *, cash=0, other=0, income=0, purchases=0, refunds=0, known=0, unknown=0
):
    return {
        "currency": code,
        "currency_fraction_digits": 2,
        "assets_minor": str(cash + other),
        "cash_minor": str(cash),
        "other_assets_minor": str(other),
        "debts_minor": "0",
        "net_worth_minor": str(cash + other),
        "recorded_spending_minor": str(purchases),
        "gross_income_minor": str(income),
        "gross_purchases_minor": str(purchases),
        "refunds_minor": str(refunds),
        "net_spending_minor": str(purchases - refunds),
        "known_accounts": known,
        "unknown_accounts": unknown,
    }


def snapshot(phase, rows):
    return {
        "api_url": readback.API,
        "phase": phase,
        "owner_hash": "a" * 64,
        "coverage": "recorded_only",
        "period": {"month": "2026-10", "time_zone": readback.ZONE},
        "currencies": rows,
    }


class MoneyReadbackTests(unittest.TestCase):
    def test_native_journey_deltas(self):
        outcomes = {
            "income": [
                row(cash=190000, income=110000, purchases=27500, refunds=7500, known=1)
            ],
            "transfer": [row(cash=97500, purchases=12500, known=2)],
            "card": [
                row(cash=80000, other=3000, purchases=12000, refunds=25000, known=2)
            ],
            "currencies": [
                row(cash=150000, known=2),
                row("USD", income=10000, refunds=2500, unknown=1),
            ],
        }
        for journey, rows in outcomes.items():
            with self.subTest(journey=journey):
                result = readback.verify(
                    snapshot("before", []), snapshot("after", rows), journey
                )
                self.assertTrue(result["passed"])

    def test_reused_account_and_unrelated_currency(self):
        before = snapshot(
            "before", [row(cash=50000, known=3), row("EUR", cash=9800, known=1)]
        )
        after = snapshot(
            "after",
            [row(cash=147500, purchases=12500, known=5), row("EUR", cash=9800, known=1)],
        )
        self.assertTrue(readback.verify(before, after, "transfer")["passed"])
        after["currencies"][1]["cash_minor"] = "9801"
        with self.assertRaisesRegex(ValueError, "EUR cash_minor delta 1; expected 0"):
            readback.verify(before, after, "transfer")

    def test_wrong_delta(self):
        after = snapshot("after", [row(cash=97500, purchases=12500, known=2)])
        after["currencies"][0]["gross_income_minor"] = "1"
        with self.assertRaisesRegex(
            ValueError, "DOP gross_income_minor delta 1; expected 0"
        ):
            readback.verify(snapshot("before", []), after, "transfer")

    def test_malformed_amount_is_not_an_empty_currency(self):
        for value in (None, 0, "0.5"):
            with self.subTest(value=value):
                invalid = row()
                invalid["refunds_minor"] = value
                with self.assertRaises(ValueError):
                    readback.currencies([invalid])

    def test_capture_omits_secrets_and_activity(self):
        requested = []

        def respond(request):
            requested.append((request.method, str(request.url)))
            if request.method == "POST":
                return httpx.Response(
                    200,
                    json={
                        "access_token": "PRIVATE_TOKEN",
                        "user": {"id": "PRIVATE_OWNER"},
                    },
                )
            home = snapshot("before", [row()])
            home["recent_activity"] = [{"note": "PRIVATE_NOTE"}]
            return httpx.Response(200, json=home)

        with tempfile.TemporaryDirectory() as directory:
            fixture, output = (
                Path(directory) / "login.json",
                Path(directory) / "snapshot.json",
            )
            fixture.write_text(
                json.dumps(
                    {
                        "apiURL": readback.API,
                        "supabaseURL": readback.AUTH,
                        "anonKey": "sb_publishable_test",
                        "email": "PRIVATE_EMAIL",
                        "password": "PRIVATE_PASSWORD",
                    }
                )
            )
            fixture.chmod(0o600)
            args = argparse.Namespace(
                fixture=fixture, output=output, month="2026-10", phase="before"
            )
            client = httpx.Client(
                transport=httpx.MockTransport(respond), follow_redirects=False
            )
            with patch.object(readback.httpx, "Client", return_value=client) as factory:
                readback.capture(args)
            self.assertFalse(factory.call_args.kwargs["follow_redirects"])
            self.assertEqual(
                requested,
                [
                    ("POST", readback.AUTH + "/auth/v1/token?grant_type=password"),
                    (
                        "GET",
                        readback.API
                        + "/financial-home?month=2026-10&time_zone=America%2FSanto_Domingo",
                    ),
                ],
            )
            self.assertNotIn("PRIVATE_", output.read_text())
            self.assertEqual(json.loads(output.read_text())["currencies"], [row()])


if __name__ == "__main__":
    unittest.main()
