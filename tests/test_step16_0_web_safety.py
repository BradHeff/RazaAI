"""Public-web safety and parsing tests."""

import socket
from unittest.mock import patch

from app.tools.web import (
    _DuckDuckGoParser,
    _TextExtractor,
    _clean_search_url,
    validate_public_url,
)


def _public_dns(*args, **kwargs):
    return [
        (
            socket.AF_INET,
            socket.SOCK_STREAM,
            6,
            "",
            ("93.184.216.34", 443),
        )
    ]


def _private_dns(*args, **kwargs):
    return [
        (
            socket.AF_INET,
            socket.SOCK_STREAM,
            6,
            "",
            ("192.168.1.1", 443),
        )
    ]


def main():
    print("=" * 56)
    print("RazaAI Step 16.0 Public Web Safety")
    print("=" * 56)

    with patch("app.tools.web.socket.getaddrinfo", _public_dns):
        assert validate_public_url("https://example.com/test") == "https://example.com/test"
    print("[PASS] public HTTPS destination accepted")

    with patch("app.tools.web.socket.getaddrinfo", _private_dns):
        try:
            validate_public_url("https://internal.example/test")
        except ValueError as exc:
            assert "private/non-public" in str(exc)
        else:
            raise AssertionError("private destination was not blocked")
    print("[PASS] private resolved destination blocked")

    for url in (
        "http://localhost/admin",
        "file:///etc/passwd",
        "https://user:pass@example.com/",
    ):
        try:
            validate_public_url(url)
        except ValueError:
            pass
        else:
            raise AssertionError(f"unsafe URL accepted: {url}")
    print("[PASS] localhost/non-http/embedded-credential URLs blocked")

    parser = _DuckDuckGoParser()
    parser.feed(
        """
        <a class="result__a" href="https://example.com/a">Example Result</a>
        <a class="result__snippet">Useful snippet text.</a>
        """
    )
    parser.close()
    assert parser.results[0]["title"] == "Example Result"
    assert "Useful snippet" in parser.results[0]["snippet"]
    print("[PASS] search result parser extracts title/snippet")

    extractor = _TextExtractor()
    extractor.feed(
        "<html><head><title>Page</title><script>bad()</script></head>"
        "<body><h1>Hello</h1><p>Readable text.</p></body></html>"
    )
    extractor.close()
    title, text = extractor.result()
    assert title == "Page"
    assert "Readable text" in text
    assert "bad()" not in text
    print("[PASS] webpage text extraction drops scripts")

    assert _clean_search_url(
        "https://duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fdoc"
    ) == "https://example.com/doc"
    print("[PASS] search redirect URLs unwrap to source URL")

    print()
    print("=" * 56)
    print("STEP 16.0 PUBLIC WEB SAFETY PASSED")
    print("=" * 56)


if __name__ == "__main__":
    main()
