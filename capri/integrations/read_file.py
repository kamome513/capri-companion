"""Drop a file on her and she reads it (2.3.4): text files, Word documents, PDFs and pictures.

What's in the file goes to your AI (only because you dropped it on her) so she can tell you what it is. Her answer is
only ever shown and said - never acted on, whatever the file says - so a document can't make her do things.
"""

from __future__ import annotations

import base64
import re
import zipfile
import zlib
from dataclasses import dataclass
from pathlib import Path

TEXT = {".txt", ".md", ".csv", ".json", ".log", ".ini", ".cfg", ".yaml", ".yml", ".xml", ".html", ".htm", ".py",
        ".js", ".ts", ".css", ".java", ".c", ".cpp", ".h", ".cs", ".lua", ".rs", ".go", ".sh", ".bat", ".ps1", ".toml",
        ".srt", ".tex", ".rtf"}
IMAGES = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}
MAX_TEXT = 12_000          # characters sent to the AI (a few pages)
MAX_READ = 4_000_000       # bytes read from a file


@dataclass
class FileContent:
    name: str
    kind: str              # "text" | "word" | "pdf" | "image" | "other"
    text: str = ""
    image_b64: str = ""    # JPEG, for pictures
    facts: str = ""        # what she can say without an AI ("a PDF, 12 pages, about 3,400 words")
    cut: bool = False      # the text was longer than what she sends


def read(path: str) -> FileContent:
    p = Path(path)
    name, ext = p.name, p.suffix.lower()
    if not p.is_file():
        return FileContent(name, "other", facts="that isn't a file I can open")
    size = p.stat().st_size
    if ext in IMAGES:
        return _image(p)
    try:
        raw = p.open("rb").read(MAX_READ)
    except OSError as exc:
        return FileContent(name, "other", facts=f"I couldn't open it ({exc.strerror or exc})")
    if ext == ".docx":
        return _finish(FileContent(name, "word"), word_text(raw), "a Word document")
    if ext == ".pdf":
        text, pages = pdf_text(raw)
        content = _finish(FileContent(name, "pdf"), text,
                          f"a PDF, {pages} page{'s' if pages != 1 else ''}" if pages else "a PDF")
        if not text:
            content.facts += " - its text is drawn as pictures or in a font I can't read"
        return content
    if ext in TEXT or _looks_like_text(raw):
        return _finish(FileContent(name, "text"), _decode(raw), f"a {ext[1:].upper() or 'text'} file")
    return FileContent(name, "other", facts=f"a {ext[1:].upper() or 'file'} file, {_size(size)}")


def _finish(content: FileContent, text: str, what: str) -> FileContent:
    text = re.sub(r"[ \t]+", " ", text or "").strip()
    words = len(text.split())
    content.cut = len(text) > MAX_TEXT
    content.text = text[:MAX_TEXT]
    content.facts = what + (f", about {words:,} words" if words else "")
    return content


def _decode(raw: bytes) -> str:
    for enc in ("utf-8-sig", "utf-16") if raw[:2] in (b"\xff\xfe", b"\xfe\xff") else ("utf-8-sig", "cp1252"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", "replace")


def _looks_like_text(raw: bytes) -> bool:
    head = raw[:4096]
    return bool(head) and b"\x00" not in head and sum(32 <= b < 127 or b in (9, 10, 13) for b in head) > 0.9 * len(head)


def _size(n: int) -> str:
    return f"{n / 1024 ** 2:.1f} MB" if n >= 1024 ** 2 else f"{max(1, n // 1024)} KB"


def word_text(raw: bytes) -> str:
    """The text of a .docx (it's a zip with the words in word/document.xml)."""
    import io
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            xml = z.read("word/document.xml").decode("utf-8", "replace")
    except (zipfile.BadZipFile, KeyError, OSError):
        return ""
    xml = re.sub(r"</w:p>", "\n", xml)
    xml = re.sub(r"<w:tab/>", "\t", xml)
    text = re.sub(r"<[^>]+>", "", xml)
    for a, b in (("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"), ("&quot;", '"'), ("&apos;", "'")):
        text = text.replace(a, b)
    return text


def pdf_text(raw: bytes) -> tuple[str, int]:
    """(text, pages) from a PDF: the words in its text commands, from each (usually compressed) page stream.
    Works for most PDFs that contain real text; scanned pages and some fonts give nothing (then "")."""
    pages = len(re.findall(rb"/Type\s*/Page(?!s)", raw))
    parts = []
    for m in re.finditer(rb"<<(.{0,600}?)>>\s*stream\r?\n", raw, re.S):
        start = m.end()
        end = raw.find(b"endstream", start)
        if end < 0:
            continue
        data = raw[start:end]
        if b"/FlateDecode" in m.group(1):
            try:
                data = zlib.decompressobj().decompress(data)
            except zlib.error:
                continue
        elif b"/Filter" in m.group(1):
            continue                                       # images and other encodings: not text
        if b"Tj" in data or b"TJ" in data:
            parts.append(_text_ops(data))
    text = "\n".join(p for p in parts if p.strip())
    letters = sum(ch.isalpha() for ch in text)
    if not text or letters < 0.5 * len(text.replace(" ", "").replace("\n", "")):
        return "", pages                                  # gibberish: a font with its own codes
    return text, pages


def _text_ops(data: bytes) -> str:
    out = []
    for m in re.finditer(rb"\[(.*?)\]\s*TJ|(\((?:\\.|[^\\)])*\))\s*(?:Tj|'|\")|(T\*|Td|TD|ET)", data, re.S):
        if m.group(3):
            out.append("\n" if m.group(3) in (b"ET", b"T*") else " ")
            continue
        chunk = m.group(1) if m.group(1) is not None else m.group(2)
        for lit in re.finditer(rb"\(((?:\\.|[^\\)])*)\)|(-?\d+(?:\.\d+)?)", chunk):
            if lit.group(1) is not None:
                out.append(_pdf_string(lit.group(1)))
            elif lit.group(2) is not None and float(lit.group(2)) < -200:
                out.append(" ")                            # a big gap in a TJ array: a space between words
    return re.sub(r" {2,}", " ", "".join(out))


def _pdf_string(s: bytes) -> str:
    out, i = bytearray(), 0
    while i < len(s):
        c = s[i]
        if c == 0x5C and i + 1 < len(s):                   # backslash escapes
            n = s[i + 1]
            simple = {ord("n"): 10, ord("r"): 13, ord("t"): 9, ord("b"): 8, ord("f"): 12, ord("("): 40,
                      ord(")"): 41, ord("\\"): 92}
            if n in simple:
                out.append(simple[n])
                i += 2
                continue
            m = re.match(rb"[0-7]{1,3}", s[i + 1:i + 4])
            if m:
                out.append(int(m.group(0), 8) & 0xFF)
                i += 1 + len(m.group(0))
                continue
            i += 2
            continue
        out.append(c)
        i += 1
    return out.decode("cp1252", "replace")


def _image(p: Path) -> FileContent:
    from PySide6.QtCore import QBuffer, QByteArray, QIODevice, Qt
    from PySide6.QtGui import QImage
    img = QImage(str(p))
    if img.isNull():
        return FileContent(p.name, "other", facts="a picture I couldn't open")
    facts = f"a picture, {img.width()} by {img.height()}"
    if max(img.width(), img.height()) > 1280:
        img = img.scaled(1280, 1280, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
    data = QByteArray()
    buf = QBuffer(data)
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    img.convertToFormat(QImage.Format.Format_RGB888).save(buf, "JPEG", 85)
    buf.close()
    return FileContent(p.name, "image", image_b64=base64.b64encode(bytes(data)).decode("ascii"), facts=facts)
