from __future__ import annotations

from pathlib import Path

S1_RUNTIME_PROSE_FILES = (
    Path("src/argus/agent_runtime/stages/explain.py"),
    Path("src/argus/api/chat/confirmation.py"),
    Path("src/argus/api/chat/confirmation_lifecycle.py"),
    Path("src/argus/api/chat/confirmation_research_peers.py"),
)

BANNED_S1_RUNTIME_LANGUAGE_PATTERNS = (
    "_is_spanish",
    'Literal["en", "es-419"]',
    '"es-419"',
    "starts with 'es'",
    'starts with "es"',
)

INLINE_SPANISH_COPY_MARKERS = (
    "Resumen",
    "Prueba siguiente",
    "Supuestos",
    "Referencia",
    "Sin comisiones",
    "Sin deslizamiento",
    "Listo para",
    "Necesita",
)


def test_issue_154_s1_runtime_prose_has_no_language_gates_or_spanish_copy() -> None:
    offenders: list[str] = []
    repo_root = Path(__file__).resolve().parents[2]
    for relative_path in S1_RUNTIME_PROSE_FILES:
        text = (repo_root / relative_path).read_text(encoding="utf-8")
        for marker in (
            *BANNED_S1_RUNTIME_LANGUAGE_PATTERNS,
            *INLINE_SPANISH_COPY_MARKERS,
        ):
            if marker in text:
                offenders.append(f"{relative_path}: {marker}")

    assert offenders == []
