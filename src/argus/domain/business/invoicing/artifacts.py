from __future__ import annotations

import asyncio
import re
import shutil
from decimal import Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lxml.etree import _Element

from argus.domain.business.fiscal_sandbox.contracts import Case


async def verify_pdf(raw: bytes, case: Case) -> None:
    executable = shutil.which("pdftotext")
    if executable is None:
        raise ValueError("invoice_pdf_parser_unavailable")
    process = await asyncio.create_subprocess_exec(
        executable,
        "-layout",
        "-",
        "-",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )

    async def write() -> None:
        process.stdin.write(raw)
        await process.stdin.drain()
        process.stdin.close()

    async def read() -> bytes:
        result = bytearray()
        while chunk := await process.stdout.read(65536):
            result.extend(chunk)
            if len(result) > 2 * 1024 * 1024:
                raise ValueError("invoice_pdf_text_size")
        return bytes(result)

    try:
        _, text = await asyncio.wait_for(asyncio.gather(write(), read()), timeout=5)
        await asyncio.wait_for(process.wait(), timeout=2)
        if process.returncode:
            raise ValueError("invoice_pdf_invalid")
        verify_pdf_text(text.decode("utf-8", errors="strict"), case)
    finally:
        if process.returncode is None:
            process.kill()
        await process.wait()


def verify_pdf_text(text: str, case: Case) -> None:
    total = Decimal(str(case.payload["totals"]["totalAmount"]))
    representations = {format(total, ".2f"), format(total, ",.2f")}
    representations |= {
        v.translate(str.maketrans({",": ".", ".": ","})) for v in list(representations)
    }
    identities = {
        value.replace("-", "")
        for value in re.findall(r"(?<!\d)\d[\d-]{7,12}\d(?!\d)", text)
    }
    if (
        not re.search(r"(?<![A-Z0-9])" + re.escape(case.number) + r"(?![A-Z0-9])", text)
        or case.issuer not in identities
        or not any(
            re.search(r"(?<![\d.,])" + re.escape(value) + r"(?![\d.,])", text)
            for value in representations
        )
        or not re.search(r"\bDOP\b|RD\$", text)
    ):
        raise ValueError("invoice_pdf_identity")


def verify_xml(document: _Element, case: Case) -> None:
    expected = [("Totales", "MontoTotal", str(case.payload["totals"]["totalAmount"]))]
    buyer_id = case.payload.get("buyer", {}).get("rnc")
    if buyer_id:
        expected.append(("Comprador", "RNCComprador", buyer_id))
    for parent, field, value in expected:
        found = document.xpath(
            "./*[local-name()='Encabezado']/*[local-name()=$parent]/*[local-name()=$field]",
            parent=parent,
            field=field,
        )
        if len(found) != 1 or len(found[0]) or found[0].text is None:
            raise ValueError("invoice_xml_identity")
        if field == "MontoTotal":
            if Decimal(found[0].text) != Decimal(value):
                raise ValueError("invoice_xml_total")
        elif found[0].text != value:
            raise ValueError("invoice_xml_buyer")
    if document.xpath("./*[local-name()='Encabezado']/*[local-name()='OtraMoneda']"):
        raise ValueError("invoice_xml_currency")
