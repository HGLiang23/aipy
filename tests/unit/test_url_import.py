"""Unit tests for the URL importer's HTML extraction and its SSRF guard.

Everything here runs without a network: only the pure helpers and the address
checks are exercised, which is exactly the part that must not regress.
"""

import pytest

from apps.api.url_import import UrlImportError, assert_public_url, extract_metadata

HTML = """
<!doctype html>
<html><head>
<title>  AI&nbsp;内容 &amp; 品牌策略 </title>
<meta name="description" content="一份关于生成式搜索与内容可信度的报告。">
</head><body><p>ignored</p></body></html>
"""


def test_extract_metadata_reads_title_and_description() -> None:
    metadata = extract_metadata(HTML, "https://research.example.com/report")

    assert metadata.title == "AI 内容 & 品牌策略"
    assert metadata.description == "一份关于生成式搜索与内容可信度的报告。"
    assert metadata.host == "research.example.com"


def test_extract_metadata_accepts_reversed_meta_attribute_order() -> None:
    document = '<meta content="来自 og 的摘要" property="og:description">'

    metadata = extract_metadata(document, "https://example.com/a")

    assert metadata.description == "来自 og 的摘要"


def test_extract_metadata_falls_back_to_the_last_path_segment() -> None:
    metadata = extract_metadata("<html><body>no title</body></html>", "https://ex.com/notes/x")

    assert metadata.title == "x"


def test_extract_metadata_falls_back_to_the_host_when_the_path_is_empty() -> None:
    metadata = extract_metadata("", "https://ex.com/")

    assert metadata.title == "ex.com"


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "ftp://example.com/a",
        "gopher://example.com",
        "https://",
    ],
)
def test_assert_public_url_rejects_unsupported_targets(url: str) -> None:
    with pytest.raises(UrlImportError):
        assert_public_url(url)


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:8000/admin",
        "http://localhost/",
        "http://10.0.0.5/",
        "http://192.168.1.1/",
        "http://172.16.4.4/",
        "http://169.254.169.254/latest/meta-data/",
        "http://[::1]/",
    ],
)
def test_assert_public_url_rejects_private_and_reserved_addresses(url: str) -> None:
    """A URL import must never become a way to probe the deployment's own network."""

    with pytest.raises(UrlImportError):
        assert_public_url(url)


def test_assert_public_url_accepts_a_public_address() -> None:
    assert_public_url("http://93.184.216.34/")
