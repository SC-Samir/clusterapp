from app.core.services.content_processing import (
    build_embedding_text,
    make_preview,
    sentence_chunks,
    strip_html,
)


def test_strip_html_basic():
    assert strip_html("<p>Hello <b>world</b></p>") == "Hello world"


def test_strip_html_decodes_entities_and_removes_encoded_tags():
    raw = "&lt;a href='https://example.com'&gt;link&lt;/a&gt; &amp; text"
    assert strip_html(raw) == "link & text"


def test_strip_html_removes_html_comments():
    raw = "<!-- SC_OFF --><div><p>Hello</p></div>"
    assert strip_html(raw) == "Hello"


def test_sentence_chunking_limits():
    text = "A short sentence. " * 100
    chunks = sentence_chunks(text, max_chars=60, max_chunks=3)
    assert len(chunks) <= 3
    assert all(len(c) <= 60 for c in chunks)


def test_build_embedding_text_includes_title_and_content():
    # build_embedding_text expects already-cleaned content (as produced by the
    # ingestion pipeline); the title is re-stripped defensively.
    out = build_embedding_text("Title", "First sentence. Second sentence.")
    assert "Title" in out
    assert "First sentence" in out


def test_make_preview_truncates_on_word_boundary():
    cleaned = "word " * 100
    preview = make_preview(cleaned, max_chars=30)
    assert len(preview) <= 31  # 30 chars + ellipsis
    assert preview.endswith("…")


def test_make_preview_returns_full_when_short():
    assert make_preview("short text") == "short text"
