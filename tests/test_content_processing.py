from app.services.content_processing import build_embedding_text, sentence_chunks, strip_html


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
    out = build_embedding_text("<h1>Title</h1>", "<p>First sentence. Second sentence.</p>")
    assert "Title" in out
    assert "First sentence" in out
