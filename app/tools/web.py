"""RazaAI read-only public web access."""

from __future__ import annotations

from datetime import datetime, timezone
from html import unescape
from html.parser import HTMLParser
import ipaddress
import json
import os
from pathlib import Path
import re
import socket
from urllib import parse, request


DEFAULT_TIMEOUT = float(os.getenv("RAZAAI_WEB_TIMEOUT", "12"))
DEFAULT_MAX_BYTES = int(os.getenv("RAZAAI_WEB_MAX_BYTES", "1048576"))
DEFAULT_MAX_RESULTS = 5
MAX_RESULTS = 10
MAX_QUERY_CHARS = 500
USER_AGENT = os.getenv(
    "RAZAAI_WEB_USER_AGENT",
    "RazaAI/0.1 (+read-only web research)",
)

ALLOWED_CONTENT_TYPES = (
    "text/html",
    "text/plain",
    "application/xhtml+xml",
    "application/json",
)

WEB_SEARCH_METADATA = {
    "name": "search_web",
    "category": "web",
    "risk": "read_only_external",
    "permission": "automatic",
    "timeout": 20,

    "model_exposed": False,
}

WEB_FETCH_METADATA = {
    "name": "fetch_web_page",
    "category": "web",
    "risk": "read_only_external",
    "permission": "automatic",
    "timeout": 20,
    "model_exposed": False,
}


def _project_root():
    return Path(__file__).resolve().parent.parent.parent


def _web_log_path():
    return _project_root() / "logs" / "web-access.jsonl"


def _audit_log(event):
    """Persist metadata/provenance only; never full fetched page contents."""
    path = _web_log_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **event,
        }
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError:
        # Web access should not fail merely because logging is unavailable.
        pass


def _is_public_ip(value):
    ip = ipaddress.ip_address(value)
    return not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def validate_public_url(url):
    """Validate an HTTP(S) URL and resolve it only to public IP addresses."""
    if not isinstance(url, str) or not url.strip():
        raise ValueError("A URL is required")

    candidate = url.strip()
    parsed = parse.urlsplit(candidate)

    if parsed.scheme.lower() not in {"http", "https"}:
        raise ValueError("Only http:// and https:// URLs are allowed")

    if parsed.username is not None or parsed.password is not None:
        raise ValueError("URLs containing embedded credentials are not allowed")

    hostname = parsed.hostname
    if not hostname:
        raise ValueError("URL must contain a hostname")

    if hostname.lower() in {"localhost", "localhost.localdomain"}:
        raise ValueError("Local/private network URLs are blocked")

    port = parsed.port or (443 if parsed.scheme.lower() == "https" else 80)

    try:
        addresses = socket.getaddrinfo(
            hostname,
            port,
            type=socket.SOCK_STREAM,
        )
    except socket.gaierror as exc:
        raise ValueError(f"Could not resolve web host: {hostname}") from exc

    resolved = []
    for item in addresses:
        address = item[4][0]
        if address not in resolved:
            resolved.append(address)

    if not resolved:
        raise ValueError(f"Could not resolve web host: {hostname}")

    for address in resolved:
        if not _is_public_ip(address):
            raise ValueError(
                f"Blocked private/non-public web destination: {hostname} -> {address}"
            )

    return candidate


class _SafeRedirectHandler(request.HTTPRedirectHandler):
    def redirect_request(
        self,
        req,
        fp,
        code,
        msg,
        headers,
        newurl,
    ):
        safe_url = validate_public_url(newurl)
        return super().redirect_request(
            req,
            fp,
            code,
            msg,
            headers,
            safe_url,
        )


def _safe_opener():
    return request.build_opener(_SafeRedirectHandler())


class _TextExtractor(HTMLParser):
    SKIP = {"script", "style", "noscript", "svg"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.skip_depth = 0
        self.parts = []
        self.title_parts = []
        self.in_title = False

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag in self.SKIP:
            self.skip_depth += 1
        if tag == "title":
            self.in_title = True

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in self.SKIP and self.skip_depth:
            self.skip_depth -= 1
        if tag == "title":
            self.in_title = False

    def handle_data(self, data):
        if self.skip_depth:
            return
        text = " ".join(data.split())
        if not text:
            return
        self.parts.append(text)
        if self.in_title:
            self.title_parts.append(text)

    def result(self):
        return (
            " ".join(self.title_parts).strip(),
            re.sub(r"\s+", " ", " ".join(self.parts)).strip(),
        )


class _DuckDuckGoParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.results = []
        self._current = None
        self._capture_title = False
        self._capture_snippet = False
        self._title_parts = []
        self._snippet_parts = []

    @staticmethod
    def _attrs(attrs):
        return dict(attrs)

    def handle_starttag(self, tag, attrs):
        attrs = self._attrs(attrs)
        classes = set((attrs.get("class") or "").split())

        if tag == "a" and "result__a" in classes:
            if self._current:
                self._finish_current()
            self._current = {"href": attrs.get("href") or ""}
            self._capture_title = True
            self._title_parts = []

        elif self._current and (
            "result__snippet" in classes
            or "result-snippet" in classes
        ):
            self._capture_snippet = True
            self._snippet_parts = []

    def handle_endtag(self, tag):
        if tag == "a" and self._capture_title:
            self._capture_title = False

        if tag in {"a", "div", "span"} and self._capture_snippet:
            self._capture_snippet = False
            self._finish_current()

    def handle_data(self, data):
        if self._capture_title:
            self._title_parts.append(data)
        if self._capture_snippet:
            self._snippet_parts.append(data)

    def close(self):
        super().close()
        if self._current:
            self._finish_current()

    def _finish_current(self):
        if not self._current:
            return

        title = " ".join(
            " ".join(self._title_parts).split()
        ).strip()
        snippet = " ".join(
            " ".join(self._snippet_parts).split()
        ).strip()

        if title and self._current.get("href"):
            self.results.append(
                {
                    "title": title,
                    "url": self._current["href"],
                    "snippet": snippet,
                }
            )

        self._current = None
        self._title_parts = []
        self._snippet_parts = []
        self._capture_title = False
        self._capture_snippet = False


def _clean_search_url(url):
    """Unwrap DuckDuckGo redirect links when possible."""
    value = unescape(url or "").strip()

    if value.startswith("//"):
        value = "https:" + value

    parsed = parse.urlsplit(value)
    query = parse.parse_qs(parsed.query)

    if "uddg" in query and query["uddg"]:
        value = query["uddg"][0]

    if not value.startswith(("http://", "https://")):
        return None

    # Do not DNS-resolve every search result here. fetch_web_page performs
    # full public-IP validation before network access.
    return value


def _bounded_read(response, max_bytes):
    declared = response.headers.get("Content-Length")
    if declared:
        try:
            if int(declared) > max_bytes:
                raise ValueError(
                    f"Web response exceeds maximum size of {max_bytes} bytes"
                )
        except ValueError as exc:
            if "exceeds maximum" in str(exc):
                raise

    data = response.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise ValueError(
            f"Web response exceeds maximum size of {max_bytes} bytes"
        )
    return data


def _require_online():
    """Fail in ~1 s with a clear reason instead of hanging for the HTTP timeout."""
    from ..connectivity import is_online, offline_reason
    if not is_online():
        raise ValueError(f"Offline: {offline_reason()}. Web search and page retrieval are unavailable until the device has internet.")


def search_web(query, max_results=DEFAULT_MAX_RESULTS):
    """Search the public web and return provenance-bearing result snippets."""
    if os.getenv("RAZAAI_WEB_ENABLED", "1").strip().lower() in {"0", "false", "no"}:
        raise ValueError("Web access is disabled by RAZAAI_WEB_ENABLED")
    _require_online()

    query = str(query or "").strip()
    if not query:
        raise ValueError("A web search query is required")
    if len(query) > MAX_QUERY_CHARS:
        raise ValueError(
            f"Web search query exceeds {MAX_QUERY_CHARS} characters"
        )

    max_results = max(1, min(int(max_results), MAX_RESULTS))

    endpoint = "https://html.duckduckgo.com/html/"
    body = parse.urlencode({"q": query}).encode("utf-8")
    req = request.Request(
        endpoint,
        data=body,
        headers={
            "User-Agent": USER_AGENT,
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )

    try:
        with request.urlopen(req, timeout=DEFAULT_TIMEOUT) as response:
            raw = _bounded_read(response, DEFAULT_MAX_BYTES)
            charset = response.headers.get_content_charset() or "utf-8"
            html = raw.decode(charset, errors="replace")
    except Exception as exc:
        _audit_log(
            {
                "action": "search",
                "provider": "duckduckgo-html",
                "query": query,
                "success": False,
                "error": str(exc),
            }
        )
        raise RuntimeError(f"Web search failed: {exc}") from exc

    parser = _DuckDuckGoParser()
    parser.feed(html)
    parser.close()

    results = []
    seen = set()

    for item in parser.results:
        url = _clean_search_url(item["url"])
        if not url or url in seen:
            continue
        seen.add(url)

        source_id = f"S{len(results) + 1}"
        results.append(
            {
                "source_id": source_id,
                "citation": f"[{source_id}]",
                "title": item["title"],
                "url": url,
                "snippet": item["snippet"],
            }
        )

        if len(results) >= max_results:
            break

    # Mark likely first-party/authoritative results for
    # release/version/advisory questions. This does not fabricate authority;
    # it only annotates domain characteristics for downstream ranking.
    authority_terms = (
        "release",
        "version",
        "firmware",
        "advisory",
        "documentation",
        "docs",
        "cve",
        "security",
    )
    authority_query = any(term in query.casefold() for term in authority_terms)

    for item in results:
        host = (parse.urlsplit(item["url"]).hostname or "").casefold()
        title = item.get("title", "").casefold()

        first_party_hint = any(
            marker in host
            for marker in (
                "fortinet.com",
                "arubanetworks.com",
                "hpe.com",
                "qwenlm.ai",
                "qwen.ai",
                "huggingface.co",
                "github.com",
                "microsoft.com",
                "learn.microsoft.com",
                "redhat.com",
                "ubuntu.com",
                "debian.org",
                "python.org",
            )
        )

        item["authority"] = (
            "preferred"
            if authority_query and first_party_hint
            else "normal"
        )

    if authority_query:
        results.sort(
            key=lambda item: (
                item.get("authority") != "preferred",
                int(item["source_id"][1:]),
            )
        )

        # Renumber source IDs after ranking so citations remain contiguous.
        for index, item in enumerate(results, 1):
            item["source_id"] = f"S{index}"
            item["citation"] = f"[S{index}]"

    payload = {
        "query": query,
        "provider": "duckduckgo-html",
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "result_count": len(results),
        "results": results,
    }

    _audit_log(
        {
            "action": "search",
            "provider": payload["provider"],
            "query": query,
            "success": True,
            "result_count": len(results),
            "domains": [
                parse.urlsplit(item["url"]).hostname
                for item in results
            ],
        }
    )

    return payload


def fetch_web_page(url, max_chars=12000):
    _require_online()
    """Fetch text from one public webpage after SSRF/private-network validation."""
    if os.getenv("RAZAAI_WEB_ENABLED", "1").strip().lower() in {"0", "false", "no"}:
        raise ValueError("Web access is disabled by RAZAAI_WEB_ENABLED")

    safe_url = validate_public_url(url)
    max_chars = max(500, min(int(max_chars), 30000))

    req = request.Request(
        safe_url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,text/plain,application/xhtml+xml,application/json;q=0.8",
        },
        method="GET",
    )

    opener = _safe_opener()

    try:
        with opener.open(req, timeout=DEFAULT_TIMEOUT) as response:
            final_url = validate_public_url(response.geturl())
            content_type = (
                response.headers.get_content_type()
                or "application/octet-stream"
            ).lower()

            if not any(
                content_type.startswith(value)
                for value in ALLOWED_CONTENT_TYPES
            ):
                raise ValueError(
                    f"Unsupported web content type: {content_type}"
                )

            raw = _bounded_read(response, DEFAULT_MAX_BYTES)
            charset = response.headers.get_content_charset() or "utf-8"
            body = raw.decode(charset, errors="replace")
    except Exception as exc:
        _audit_log(
            {
                "action": "fetch",
                "url": safe_url,
                "success": False,
                "error": str(exc),
            }
        )
        raise RuntimeError(f"Web page fetch failed: {exc}") from exc

    title = ""
    if content_type.startswith(("text/html", "application/xhtml+xml")):
        parser = _TextExtractor()
        parser.feed(body)
        parser.close()
        title, text = parser.result()
    elif content_type.startswith("application/json"):
        try:
            parsed_json = json.loads(body)
            text = json.dumps(
                parsed_json,
                ensure_ascii=False,
                indent=2,
            )
        except json.JSONDecodeError:
            text = body
    else:
        text = body

    text = re.sub(r"\s+", " ", text).strip()
    truncated = len(text) > max_chars
    text = text[:max_chars]

    payload = {
        "source_id": "W1",
        "citation": "[W1]",
        "url": final_url,
        "title": title or final_url,
        "content_type": content_type,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "truncated": truncated,
        "text": text,
    }

    _audit_log(
        {
            "action": "fetch",
            "url": final_url,
            "success": True,
            "content_type": content_type,
            "characters_returned": len(text),
            "truncated": truncated,
        }
    )

    return payload


WEB_SEARCH_DEFINITION = {
    "type": "function",
    "function": {
        "name": "search_web",
        "description": (
            "Search the public internet read-only. Results include source IDs, "
            "titles, URLs, snippets, provider and retrieval time. Use only for "
            "explicit web/current-information requests. Cite source IDs in answers."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Public web search query.",
                },
                "max_results": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 10,
                    "default": 5,
                },
            },
            "required": ["query"],
        },
    },
}


WEB_FETCH_DEFINITION = {
    "type": "function",
    "function": {
        "name": "fetch_web_page",
        "description": (
            "Fetch readable text from one explicit public HTTP/HTTPS URL. "
            "Private/local network destinations are blocked. The result includes "
            "a source ID, URL, retrieval time and bounded page text."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "Explicit public HTTP/HTTPS URL.",
                },
                "max_chars": {
                    "type": "integer",
                    "minimum": 500,
                    "maximum": 30000,
                    "default": 12000,
                },
            },
            "required": ["url"],
        },
    },
}
