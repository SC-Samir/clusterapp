import html
import re
from typing import Iterable

TAG_RE = re.compile(r"<[^>]+>")
COMMENT_RE = re.compile(r"<!--.*?-->", flags=re.DOTALL)
WS_RE = re.compile(r"\s+")


def strip_html(raw: str) -> str:
    text = raw or ""
    # Some feeds escape markup (e.g. "&lt;a ...&gt;"), so decode first.
    for _ in range(2):
        text = html.unescape(text)
    text = COMMENT_RE.sub(" ", text)
    text = TAG_RE.sub(" ", text)
    return WS_RE.sub(" ", text).strip()


def sentence_chunks(text: str, max_chars: int = 700, max_chunks: int = 8) -> list[str]:
    cleaned = strip_html(text)
    if not cleaned:
        return []

    sentences = re.split(r"(?<=[.!?])\s+", cleaned)
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


def build_embedding_text(title: str, content: str) -> str:
    title_clean = strip_html(title)
    chunks = sentence_chunks(content)
    if not chunks:
        return title_clean

    # Keep first chunks to preserve intro context and avoid very long vectors input.
    joined = "\n".join(chunks)
    return f"{title_clean}\n\n{joined}".strip()
