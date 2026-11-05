"""Inline Breakdown citations are bounded by this response's returned sources."""

import json
from pathlib import Path

import pytest
from argus.domain.research.contracts import ResearchSource
from argus.domain.result_readout_sources import accepted_breakdown_text
from markdown_it import MarkdownIt

ENCODINGS = json.loads(
    (Path(__file__).parent / "fixtures/result_readouts/link_encodings.json").read_text()
)


@pytest.fixture(
    params=[
        ("en", "Quarterly results", "The company reported growth."),
        ("es-419", "Resultados trimestrales", "La empresa reportó crecimiento."),
    ]
)
def language_case(request):
    return request.param


def accept(text, language, sources):
    rendered, failure = accepted_breakdown_text(
        {"language": language, "text": text, "figures": []},
        facts={},
        language=language,
        sources=sources,
    )
    assert failure is None
    return rendered


def hrefs(text):
    return [
        child.attrGet("href")
        for block in MarkdownIt().parse(text)
        for child in block.children or []
        if child.type == "link_open"
    ]


def test_keep_descriptive_link_to_returned_source(language_case):
    language, title, sentence = language_case
    source = ResearchSource(url="https://example.com/results", title=title)
    text = f"{sentence} [{title}]({source.url})"
    assert accept(text, language, [source]) == text


@pytest.mark.parametrize("case", ENCODINGS, ids=lambda case: case["raw"])
def test_decoded_gfm_autolinks_follow_the_same_source_boundary(language_case, case):
    language, title, sentence = language_case
    source = ResearchSource(url=case["decoded"], title=title)
    sources = [source] if case.get("returned") else []
    expected = f"[{title}](<{source.url}>)" if sources else f"`{case['decoded']}`"
    assert (
        accept(sentence + " " + case["raw"], language, sources)
        == sentence + " " + expected
    )


def test_decoding_does_not_activate_unrelated_markdown_or_change_code(language_case):
    language, _, _ = language_case
    text = "&ast;words&ast; and `https&#58;//invented.example`"
    assert accept(text, language, []) == text


@pytest.mark.parametrize("shape", ["{}", "<{}>", "[{0}]({0})"])
def test_bare_returned_url_uses_source_title(language_case, shape):
    language, title, sentence = language_case
    source = ResearchSource(url="https://example.com/results", title=title)
    rendered = accept(f"{sentence} {shape.format(source.url)}.", language, [source])
    assert rendered == f"{sentence} [{title}](<{source.url}>)."
    assert hrefs(rendered) == [source.url]


@pytest.mark.parametrize(
    "shape", ["[{label}]({url})", "[{label}][cite]\n\n[cite]: {url}"]
)
def test_unreturned_link_keeps_words_without_a_link(language_case, shape):
    language, title, sentence = language_case
    text = (
        sentence + " " + shape.format(label=title, url="https://invented.example/results")
    )
    rendered = accept(text, language, [])
    assert sentence + " " + title in rendered
    assert hrefs(rendered) == []


@pytest.mark.parametrize(
    "url",
    ["https://invented.example/results", "www.invented.example", "fake@invented.example"],
)
def test_unreturned_bare_url_cannot_be_autolinked_by_gfm(language_case, url):
    language, _, sentence = language_case
    rendered = accept(sentence + " " + url, language, [])
    assert f"`{url}`" in rendered
    assert hrefs(rendered) == []


def test_normal_markdown_destinations_and_source_titles_are_not_regex_delimited(
    language_case,
):
    language, title, _ = language_case
    source = ResearchSource(
        url="https://example.com/results_(2026)?a=1&b=2", title=title + " [2026]"
    )
    rendered = accept(
        f"[read]({source.url}) [invented](https://evil.example/a_(b))", language, [source]
    )
    assert hrefs(rendered) == [source.url]
    assert rendered.endswith("invented")
    assert hrefs(accept(source.url, language, [source])) == [source.url]


def test_code_and_unrelated_formatting_are_preserved(language_case):
    language, title, sentence = language_case
    source = ResearchSource(url="https://example.com/results", title=title)
    text = f"**{sentence}**\n\n`https://example.com/code`\n\n[{title}]({source.url})"
    assert accept(text, language, [source]) == text


def test_unreturned_destination_cannot_hide_behind_a_returned_url_label(language_case):
    language, title, _ = language_case
    source = ResearchSource(url="https://example.com/a_(b)", title=title)
    rendered = accept(f"[{source.url}](https://invented.example)", language, [source])
    assert rendered == f"`{source.url}`"
    assert hrefs(rendered) == []

