import html
import re
from typing import Iterable

TAG_RE = re.compile(r"<[^>]+>")
COMMENT_RE = re.compile(r"<!--.*?-->", flags=re.DOTALL)
WS_RE = re.compile(r"\s+")
SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")

PREVIEW_DEFAULT_LENGTH = 280


def strip_html(raw: str) -> str:
    text = raw or ""
    # Some feeds escape markup (e.g. "&lt;a ...&gt;"), so decode first.
    for _ in range(2):
        text = html.unescape(text)
    text = COMMENT_RE.sub(" ", text)
    text = TAG_RE.sub(" ", text)
    return WS_RE.sub(" ", text).strip()


def make_preview(cleaned: str, max_chars: int = PREVIEW_DEFAULT_LENGTH) -> str:
    """Truncate already-cleaned text to a preview length on a word boundary."""
    if len(cleaned) <= max_chars:
        return cleaned
    cut = cleaned[:max_chars]
    # Try to break on the last whitespace within the window for a clean cut.
    space = cut.rfind(" ")
    if space > 0:
        cut = cut[:space]
    return cut.strip() + "…"


def sentence_chunks(text: str, max_chars: int = 700, max_chunks: int = 8) -> list[str]:
    """Split already-cleaned text into bounded sentence chunks.

    Caller is expected to pass already-stripped text; this avoids re-running
    strip_html on content that was already cleaned upstream.
    """
    if not text:
        return []

    sentences = SENTENCE_SPLIT_RE.split(text)
    chunks: list[str] = []
    current = ""

    for sentence in sentences:
        s = sentence.strip()
        if not s:
            continue
        if len(current) + len(s) + 1 <= max_chars:
            current = f"{current} {s}".strip()
        else:
            if current:
                chunks.append(current)
            current = s
        if len(chunks) >= max_chunks:
            break

    if current and len(chunks) < max_chunks:
        chunks.append(current)

    return chunks


def build_embedding_text(title: str, content_clean: str) -> str:
    """Build the text fed to the embedder from a clean title and clean content.

    Both inputs are expected to already be HTML-stripped. Only the title is
    re-sanitized defensively (titles are small and cheap) so callers can pass a
    raw title safely; content is reused as-is to avoid a second strip pass.
    """
    title_clean = strip_html(title)
    chunks = sentence_chunks(content_clean)
    if not chunks:
        return title_clean

    # Keep first chunks to preserve intro context and avoid very long vectors input.
    joined = "\n".join(chunks)
    return f"{title_clean}\n\n{joined}".strip()