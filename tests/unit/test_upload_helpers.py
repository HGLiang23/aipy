"""Unit tests for the small helpers behind search, upload and download."""

from apps.api.http_utils import attachment_header
from apps.api.repositories import _escape_like, _human_size, _text_preview


def test_escape_like_neutralises_metacharacters() -> None:
    """A user typing ``%`` must search for a percent sign, not match everything."""

    assert _escape_like("50%_off") == "50\\%\\_off"
    assert _escape_like("back\\slash") == "back\\\\slash"
    assert _escape_like("普通文本") == "普通文本"


def test_text_preview_decodes_utf8_text_files() -> None:
    assert _text_preview("第一行\n第二行".encode(), "notes.txt") == "第一行 第二行"


def test_text_preview_is_empty_for_binary_and_undecodable_content() -> None:
    assert _text_preview(b"%PDF-1.7", "report.pdf") == ""
    assert _text_preview(b"\xff\xfe\x00", "notes.txt") == ""


def test_text_preview_truncates_long_documents() -> None:
    preview = _text_preview(b"x" * 1000, "notes.md")

    assert len(preview) == 280


def test_human_size_scales_units() -> None:
    assert _human_size(512) == "512 B"
    assert _human_size(2048) == "2 KB"
    assert _human_size(3 * 1024 * 1024) == "3.0 MB"


def test_attachment_header_survives_a_non_ascii_title() -> None:
    header = attachment_header("AI 内容 & 品牌策略.md")

    # Headers are latin-1, so the ASCII fallback plus the RFC 5987 form are both sent.
    assert header.startswith('attachment; filename="')
    assert "filename*=UTF-8''" in header
    assert header.isascii()
