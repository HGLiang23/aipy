"""Fetch a page's title and description for the material importer.

Importing a URL is only useful if the resulting material carries something more
than the link the user typed, so this module performs a real HTTP GET and reads the
document title plus its ``meta[name=description]``.

Because the target is attacker-controlled, every hop is validated before it is
requested: the scheme must be http/https, the hostname must resolve exclusively to
*global* addresses, and redirects are followed manually so a 302 cannot smuggle the
request into the private network. Response bodies are capped. The pure extraction
helpers are separated from the I/O so they can be unit-tested without a network.
"""

import html
import ipaddress
import re
import socket
from dataclasses import dataclass
from urllib.parse import urlsplit

import httpx

#: Read at most this much of a page before giving up: title/description live in
#: ``<head>``, and the cap keeps a hostile multi-gigabyte response from being
#: buffered into memory.
MAX_BYTES = 256 * 1024
TIMEOUT_SECONDS = 5.0
MAX_REDIRECTS = 5
USER_AGENT = "AIPY-MaterialImport/1.0 (+https://example.com/bot)"

_TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_DESCRIPTION = re.compile(
    r"<meta[^>]+(?:name|property)=[\"'](?:description|og:description)[\"'][^>]*"
    r"content=[\"'](.*?)[\"']",
    re.IGNORECASE | re.DOTALL,
)
_DESCRIPTION_REVERSED = re.compile(
    r"<meta[^>]+content=[\"'](.*?)[\"'][^>]*"
    r"(?:name|property)=[\"'](?:description|og:description)[\"']",
    re.IGNORECASE | re.DOTALL,
)
_TAG = re.compile(r"<[^>]+>")
_WHITESPACE = re.compile(r"\s+")


class UrlImportError(Exception):
    """The URL could not be imported; the message is safe to show the caller."""


@dataclass(frozen=True)
class PageMetadata:
    """What the importer could learn about the page."""

    title: str
    description: str
    host: str


def _text(value: str) -> str:
    return _WHITESPACE.sub(" ", html.unescape(_TAG.sub(" ", value))).strip()


def extract_metadata(document: str, url: str) -> PageMetadata:
    """Pull the title and description out of an HTML document.

    Falls back to the host and path when the page has no usable ``<title>``, so a
    material always has a label the user can recognise.
    """

    host = urlsplit(url).hostname or url
    title_match = _TITLE.search(document)
    title = _text(title_match.group(1)) if title_match else ""
    if not title:
        title = _text(urlsplit(url).path.rsplit("/", maxsplit=1)[-1]) or host

    description_match = _DESCRIPTION.search(document) or _DESCRIPTION_REVERSED.search(document)
    description = _text(description_match.group(1)) if description_match else ""
    return PageMetadata(title=title[:255], description=description[:4000], host=host)


def assert_public_url(url: str) -> None:
    """Reject anything that is not a public http/https address.

    Raises :class:`UrlImportError` for a bad scheme, an unresolvable host, or a host
    that resolves to a loopback / private / link-local / reserved address.
    """

    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"}:
        raise UrlImportError("仅支持 http 或 https 链接")
    host = parts.hostname
    if not host:
        raise UrlImportError("链接缺少主机名")

    try:
        infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise UrlImportError(f"无法解析主机名：{host}") from exc

    for info in infos:
        address = ipaddress.ip_address(info[4][0])
        mapped = getattr(address, "ipv4_mapped", None)
        if mapped is not None:
            address = mapped
        if not address.is_global:
            raise UrlImportError("出于安全考虑，不能导入内网或保留地址")


def _read_capped(response: httpx.Response) -> str:
    chunks: list[bytes] = []
    size = 0
    for chunk in response.iter_bytes():
        chunks.append(chunk)
        size += len(chunk)
        if size >= MAX_BYTES:
            break
    raw = b"".join(chunks)
    encoding = response.encoding or "utf-8"
    return raw.decode(encoding, errors="replace")


def fetch_metadata(url: str) -> PageMetadata:
    """Fetch ``url`` and return its title/description, validating every redirect hop."""

    target = url
    for _ in range(MAX_REDIRECTS + 1):
        assert_public_url(target)
        with httpx.Client(
            follow_redirects=False,
            timeout=TIMEOUT_SECONDS,
            headers={"User-Agent": USER_AGENT, "Accept": "text/html,*/*;q=0.8"},
        ) as client:
            response = client.get(target)
        if response.is_redirect:
            location = response.headers.get("location")
            if not location:
                raise UrlImportError("目标站点返回了无目标的重定向")
            target = str(httpx.URL(target).join(location))
            continue
        if response.status_code >= 400:
            raise UrlImportError(f"目标站点返回状态码 {response.status_code}")
        return extract_metadata(_read_capped(response), target)

    raise UrlImportError("重定向次数过多")
