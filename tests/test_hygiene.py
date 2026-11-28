"""Repository hygiene checks for static XSS sinks, inline HTML assets, secrets, and size."""
import pathlib
import subprocess
import unittest
from html.parser import HTMLParser

ROOT = pathlib.Path(__file__).resolve().parents[1]
FIRST_PARTY_JS = [
    p for p in sorted((ROOT / "app" / "static").rglob("*.js")) if p.name != "leaflet.js"
]
INDEX_HTML = ROOT / "app" / "static" / "index.html"
MAX_REPO_BYTES = 1024 * 1024


class _InlineAssetParser(HTMLParser):
    """Collect inline script/style violations inside index.html."""

    def __init__(self) -> None:
        super().__init__()
        self.in_script = False
        self.violations: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = dict(attrs)
        if tag == "style":
            self.violations.append("<style> tag is forbidden")
        if "style" in attr_map:
            self.violations.append(f"inline style attribute on <{tag}>")
        if tag == "script":
            self.in_script = True
            if not attr_map.get("src"):
                self.violations.append("<script> tag without src is forbidden")

    def handle_endtag(self, tag: str) -> None:
        if tag == "script":
            self.in_script = False

    def handle_data(self, data: str) -> None:
        if self.in_script and data.strip():
            self.violations.append("inline JavaScript body inside <script>")


def _tracked_files() -> list[pathlib.Path]:
    """Return paths of tracked files in the repository."""
    res = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
        capture_output=True,
        check=True,
    )
    return [ROOT / rel for rel in res.stdout.decode("utf-8").split("\0") if rel]


class HygieneTests(unittest.TestCase):
    """Verify static security hygiene and bounded repository footprint."""

    def test_no_dom_html_sinks_in_first_party_js(self) -> None:
        sinks = ("inner" + "HTML", "insert" + "AdjacentHTML")
        self.assertGreaterEqual(len(FIRST_PARTY_JS), 8)
        for js_file in FIRST_PARTY_JS:
            text = js_file.read_text("utf-8")
            for sink in sinks:
                self.assertNotIn(sink, text, f"{sink} found in {js_file.name}")

    def test_no_inline_script_or_style_in_index_html(self) -> None:
        parser = _InlineAssetParser()
        parser.feed(INDEX_HTML.read_text("utf-8"))
        parser.close()
        self.assertEqual(parser.violations, [])

    def test_no_api_key_prefixes_in_tracked_files(self) -> None:
        prefixes = ("gsk" + "_", "AI" + "za")
        for path in _tracked_files():
            content = path.read_text("utf-8", errors="ignore")
            for prefix in prefixes:
                self.assertNotIn(prefix, content, f"Key prefix {prefix} in {path}")

    def test_tracked_repo_size_under_one_megabyte(self) -> None:
        total = sum(p.stat().st_size for p in _tracked_files() if p.is_file())
        self.assertLess(total, MAX_REPO_BYTES)


if __name__ == "__main__":
    unittest.main()
