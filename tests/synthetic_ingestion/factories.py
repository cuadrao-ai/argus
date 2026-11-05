"""Deliberate financial scenarios; Faker supplies incidental fictional labels only.

These dictionaries are provisional test scaffolding, never product contracts.
"""

from decimal import Decimal

from faker import Faker

FIELDS = (
    "source_id",
    "date",
    "description",
    "amount",
    "currency",
    "kind",
    "account",
    "destination",
)


def row(
    source_id,
    amount,
    *,
    date="2026-09-10",
    currency="DOP",
    kind="expense",
    description="Compra sintética",
    account="cash-dop",
    destination="personal",
):
    """Keep deliberate raw ambiguities; serialize known monetary values exactly."""
    return dict(
        zip(
            FIELDS,
            (
                source_id,
                date,
                description,
                format(amount, ".2f") if isinstance(amount, Decimal) else amount,
                currency,
                kind,
                account,
                destination,
            ),
            strict=True,
        )
    )


def build_corpus(seed: int = 71) -> dict:
    fake = Faker("es_ES")
    fake.seed_instance(seed)
    merchant = f"Comercio Ficticio {fake.last_name()}"
    tx = [
        row("tx-dop-01", Decimal("1200"), description="Ingreso sintético", kind="income"),
        row("tx-dop-02", Decimal("125.50"), description=merchant),
        row("tx-dop-03", Decimal("125.50"), description=merchant),
        row(
            "tx-dop-04",
            Decimal("25.50"),
            description="Devolución sintética",
            kind="refund",
        ),
        row(
            "tx-dop-05",
            Decimal("200"),
            description="Transferencia sintética",
            kind="transfer",
        ),
        row("tx-usd-01", Decimal("40"), currency="USD", account="cash-usd"),
        row("tx-currency", Decimal("30"), currency="$"),
        row("tx-date", Decimal("80"), date="03/04/2026"),
        row("tx-number", "1.234,56"),
        row("tx-missing", "", date="", account=""),
        row("tx-household", Decimal("700"), destination="personal or household"),
    ]
    manual = [
        row("manual-expense", Decimal("150"), description="Efectivo: almuerzo"),
        row(
            "manual-income",
            Decimal("1000"),
            kind="income",
            description="Efectivo: ingreso",
        ),
        row(
            "manual-transfer",
            Decimal("300"),
            kind="transfer",
            description="Efectivo a cuenta",
        ),
    ]
    statement = [
        row(
            "statement-01",
            Decimal("1200"),
            kind="income",
            description="Synthetic income",
            account="statement-dop",
        ),
        row(
            "statement-02",
            Decimal("125.50"),
            description="Synthetic purchase A",
            account="statement-dop",
        ),
        row(
            "statement-03",
            Decimal("125.50"),
            description="Synthetic purchase B",
            account="statement-dop",
        ),
        row(
            "statement-04",
            Decimal("25.50"),
            kind="refund",
            description="Synthetic refund",
            account="statement-dop",
        ),
    ]
    texts = {
        "conversation-es.txt": "SINTÉTICO. Gasté RD$350 en comida el 10 de septiembre de 2026, de mi efectivo personal. También pagué $20; no dije la moneda ni la cuenta.\n",
        "conversation-en.txt": "SYNTHETIC. I received USD 90 on 2026-09-10 in my personal cash account. What if I spent USD 20 tomorrow? That question is not a transaction.\n",
        "voice-transcript-es.txt": "TRANSCRIPCIÓN SINTÉTICA, NO AUDIO. Eh... gasté trescientos, no, doscientos cincuenta pesos dominicanos ayer... bueno, fue el diez de septiembre de 2026, de mi efectivo personal. Y setecientos de la compra de casa, no sé si ponerlo personal o del hogar.\n",
    }
    stubs = {
        "conversation-es.txt": [
            row("chat-es-01", Decimal("350")),
            row("chat-es-02", Decimal("20"), currency="$", account=""),
        ],
        "conversation-en.txt": [
            row(
                "chat-en-01",
                Decimal("90"),
                currency="USD",
                kind="income",
                account="cash-usd",
            )
        ],
        "voice-transcript-es.txt": [
            row("voice-01", Decimal("250")),
            row(
                "voice-02",
                Decimal("700"),
                date="",
                account="",
                destination="personal or household",
            ),
        ],
        "receipt.png": [
            row("receipt-01", "", description="Partially unreadable receipt")
        ],
        "scanned-statement.png": [
            row("scan-01", Decimal("500"), kind="income", account="scan-dop"),
            row("scan-02", "", date="2026-09-11", account="scan-dop"),
        ],
    }
    return {
        "seed": seed,
        "merchant": merchant,
        "transactions": tx,
        "manual": manual,
        "statement": statement,
        "texts": texts,
        "stubs": stubs,
        "overlap": [tx[0], row("overlap-new", Decimal("60"), date="2026-09-11")],
        "balances": {"opening": "1000.00", "closing": "1974.50", "currency": "DOP"},
    }
