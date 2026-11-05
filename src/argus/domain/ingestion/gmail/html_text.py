"""HTML email to plain text without rendering, executing or fetching anything.

Uses the standard library tokenizer only. Script, style, template, frame and
embedded-object content is dropped, as is content the sender marked hidden
(``hidden``, ``aria-hidden="true"`` or an inline ``display:none`` /
``visibility:hidden``), a common way to smuggle text a reader never sees.
An unclosed hidden element hides
everything after it. Images, links and stylesheets are never resolved: no URL in the message is
ever requested. Input and output are size-capped.

The result is still untrusted text: it only ever reaches a candidate through
the contract's inert-text fields.
"""

from __future__ import annotations

from html.parser import HTMLParser

MAX_HTML_CHARS = 512 * 1024
MAX_TEXT_CHARS = 64 * 1024

_DROPPED = frozenset(
    {
        "script", "style", "head", "title", "template", "noscript", "iframe",
        "frame", "frameset", "object", "embed", "applet", "svg", "math",
        "canvas", "audio", "video", "select", "textarea", "button", "xml",
    }
)  # fmt: skip
_VOID = frozenset(
    {
        "area", "base", "br", "col", "embed", "hr", "img", "input", "link",
        "meta", "param", "source", "track", "wbr",
    }
)  # fmt: skip
_BREAKS = frozenset(
    {
        "br", "p", "div", "tr", "li", "ul", "ol", "table", "h1", "h2", "h3",
        "h4", "h5", "h6", "blockquote", "section", "article", "header",
        "footer", "hr", "td", "th",
    }
)  # fmt: skip


class _TextOnly(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.size = 0
        # The tag that started the dropped region and how deeply that same
        # tag is nested inside it. Only that tag's end tags count, so a stray
        # ``</p>`` cannot end a hidden ``<div>`` early.
        self.skip_tag: str | None = None
        self.skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self.skip_tag is not None:
            if tag == self.skip_tag:
                self.skip_depth += 1
            return
        if tag in _VOID:
            if tag in _BREAKS:
                self._emit("\n")
            return
        if tag in _DROPPED or _hidden(attrs):
            self.skip_tag, self.skip_depth = tag, 1
            return
        if tag in _BREAKS:
            self._emit("\n")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self.skip_tag is None and tag in _BREAKS:
            self._emit("\n")

    def handle_endtag(self, tag: str) -> None:
        if self.skip_tag is not None:
            if tag == self.skip_tag:
                self.skip_depth -= 1
                if self.skip_depth == 0:
                    self.skip_tag = None
            return
        if tag in _BREAKS and tag not in _VOID:
            self._emit("\n")

    def handle_data(self, data: str) -> None:
        if self.skip_tag is None:
            self._emit(data)

    def _emit(self, text: str) -> None:
        if self.size >= MAX_TEXT_CHARS:
            return
        text = text[: MAX_TEXT_CHARS - self.size]
        self.parts.append(text)
        self.size += len(text)


def _hidden(attrs: list[tuple[str, str | None]]) -> bool:
    for name, value in attrs:
        if name == "hidden":
            return True
        lowered = (value or "").lower()
        if name == "aria-hidden" and lowered.strip() == "true":
            return True
        if name == "style":
            compact = "".join(lowered.split())
            if "display:none" in compact or "visibility:hidden" in compact:
                return True
    return False


def html_to_text(html: str) -> str:
    parser = _TextOnly()
    try:
        parser.feed(html[:MAX_HTML_CHARS])
        parser.close()
    except Exception:  # noqa: BLE001 - malformed markup yields what was read
        pass
    lines = (" ".join(line.split()) for line in "".join(parser.parts).splitlines())
    return "\n".join(line for line in lines if line)
