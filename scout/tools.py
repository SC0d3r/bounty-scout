"""The one tool the agent gets: a bounded, SSRF-safe public page fetcher.

A bounty listing is untrusted input. If the scout is going to read the page a
stranger linked, the read has to be boring: public HTTP(S) only, no redirects
into the local network, a hard byte cap, and text-only output.
"""

from __future__ import annotations

import html
import ipaddress
import re
import socket
import urllib.error
import urllib.parse
import urllib.request

from openminion import tool

USER_AGENT = "bounty-scout/0.1 (+https://github.com/SC0d3r/bounty-scout)"
MAX_BYTES = 120_000
MAX_CHARS = 3_000


def _is_public_host(host: str) -> bool:
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return False
    for info in infos:
        address = info[4][0]
        try:
            ip = ipaddress.ip_address(address)
        except ValueError:
            return False
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            return False
    return True


def _visible_text(raw: str) -> str:
    raw = re.sub(r"(?is)<(script|style|noscript|svg).*?</\1>", " ", raw)
    raw = re.sub(r"(?s)<[^>]+>", " ", raw)
    raw = html.unescape(raw)
    raw = re.sub(r"\s+", " ", raw).strip()
    return raw[:MAX_CHARS]


@tool
def fetch_page(url: str) -> str:
    """Fetch a public web page and return its visible text.

    Use this only to confirm that a bounty page is still live and still shows
    the reward. Returns up to 3000 characters, or a string starting with
    "ERROR:" when the page cannot be read safely.
    """

    try:
        parsed = urllib.parse.urlparse(url.strip())
    except ValueError:
        return "ERROR: invalid URL"
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return "ERROR: only public http(s) URLs are allowed"
    if not _is_public_host(parsed.hostname):
        return "ERROR: host is not public"

    request = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml,text/plain"},
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=20) as response:
            content_type = response.headers.get("Content-Type", "")
            raw = response.read(MAX_BYTES).decode("utf-8", errors="replace")
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        return f"ERROR: {type(exc).__name__}: {exc}"

    if "json" in content_type:
        return raw[:MAX_CHARS]
    return _visible_text(raw)
