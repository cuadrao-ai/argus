"""Check two local production servers, enabled on 3219 and disabled on 3218."""

import json
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen


class Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.noindex = False
        self.disabled_form = False
        self.languages = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "meta" and attrs.get("name") == "robots":
            self.noindex = "noindex" in attrs.get("content", "")
        if tag == "fieldset" and "disabled" in attrs:
            self.disabled_form = True
        if "lang" in attrs:
            self.languages.append(attrs["lang"])


routes = ["/business", "/business/demo", "/business/personal",
          "/business/en", "/business/en/demo", "/business/en/personal"]
results = []
for port, enabled in [(3219, True), (3218, False)]:
    for route in [*routes, "/business/icon.svg", "/business/missing", "/", "/dev/result-card"]:
        try:
            response = urlopen(f"http://127.0.0.1:{port}{route}", timeout=20)
        except HTTPError as error:
            response = error
        body = response.read().decode()
        allowed = route in routes or route == "/business/icon.svg"
        expected = 200 if route == "/" or (enabled and allowed) else 404
        assert response.status == expected, (port, route, response.status, expected)
        result = {"port": port, "path": route, "status": response.status}
        if enabled and route in routes:
            page = Page()
            page.feed(body)
            language = "en" if route.startswith("/business/en") else "es-DO"
            assert page.noindex and language in page.languages, (route, "metadata")
            assert "<h1" in body, (route, "missing server-rendered content")
            if route.endswith("/demo"):
                assert page.disabled_form, (route, "form active before hydration")
            result.update(noindex=True, content_language=language, server_rendered=True)
        results.append(result)
Path(__file__).with_name("http-checks.json").write_text(json.dumps(results, indent=2) + "\n")
print(f"Passed {len(results)} HTTP checks, including disabled routes and pre-hydration forms.")
