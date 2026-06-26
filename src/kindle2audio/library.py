"""Locate a book in the Calibre library and extract clean plain text from it.

Text extraction goes through Calibre's own ``ebook-convert`` for both EPUB and
PDF, which gives one uniform, well-tested path and strips most formatting chrome.
The result is cached on disk keyed by the source file's path + size + mtime, so
re-running for the same book is instant.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .state import cache_dir


class LibraryError(RuntimeError):
    """Raised for any user-facing problem locating or reading a book."""


@dataclass
class Book:
    key: str          # stable identity for resume state (calibre id or file path)
    title: str
    authors: str
    path: Path        # the source file we will read (epub/pdf)

    @property
    def fmt(self) -> str:
        return self.path.suffix.lower().lstrip(".")


def _require(tool: str) -> str:
    found = shutil.which(tool)
    if not found:
        raise LibraryError(
            f"'{tool}' was not found on PATH. It is required; install Calibre "
            f"(provides ebook-convert/calibredb)."
        )
    return found


# Formats we can read, in order of preference (EPUB converts far cleaner than PDF).
_FORMAT_PREFERENCE = (".epub", ".azw3", ".mobi", ".pdf", ".txt")


def _pick_format(paths: list[str]) -> Path | None:
    by_ext = {Path(p).suffix.lower(): Path(p) for p in paths}
    for ext in _FORMAT_PREFERENCE:
        if ext in by_ext:
            return by_ext[ext]
    return Path(paths[0]) if paths else None


def find_books(query: str) -> list[Book]:
    """Search the Calibre library by title (and author) for ``query``."""
    calibredb = _require("calibredb")
    # Search title and authors; calibredb's default search already spans both,
    # but being explicit keeps behaviour predictable.
    search = f'title:"{query}" or authors:"{query}"'
    try:
        out = subprocess.run(
            [calibredb, "list", "--for-machine", "-f", "title,authors,formats,id",
             "-s", search],
            capture_output=True, text=True, check=True,
        ).stdout
    except subprocess.CalledProcessError as e:
        raise LibraryError(f"calibredb failed: {e.stderr.strip() or e}") from e

    records = json.loads(out or "[]")
    books: list[Book] = []
    for rec in records:
        path = _pick_format(rec.get("formats") or [])
        if path is None:
            continue
        books.append(Book(
            key=f"calibre:{rec['id']}",
            title=rec.get("title", "Unknown"),
            authors=rec.get("authors", "Unknown"),
            path=path,
        ))
    return books


def book_from_id(book_id: int) -> Book:
    calibredb = _require("calibredb")
    out = subprocess.run(
        [calibredb, "list", "--for-machine", "-f", "title,authors,formats,id",
         "-s", f"id:{book_id}"],
        capture_output=True, text=True, check=True,
    ).stdout
    records = json.loads(out or "[]")
    if not records:
        raise LibraryError(f"No Calibre book with id {book_id}.")
    rec = records[0]
    path = _pick_format(rec.get("formats") or [])
    if path is None:
        raise LibraryError(f"Book id {book_id} has no readable format.")
    return Book(
        key=f"calibre:{rec['id']}",
        title=rec.get("title", "Unknown"),
        authors=rec.get("authors", "Unknown"),
        path=path,
    )


def book_from_file(file_path: str) -> Book:
    p = Path(file_path).expanduser().resolve()
    if not p.exists():
        raise LibraryError(f"File not found: {p}")
    return Book(key=f"file:{p}", title=p.stem, authors="Unknown", path=p)


def resolve_book(*, book: str | None, book_id: int | None,
                 file: str | None) -> Book:
    """Resolve a book from the various selectors, raising on ambiguity."""
    if file:
        return book_from_file(file)
    if book_id is not None:
        return book_from_id(book_id)
    if book:
        matches = find_books(book)
        if not matches:
            raise LibraryError(f"No Calibre book matched '{book}'.")
        if len(matches) > 1:
            listing = "\n".join(
                f"  - {b.title} — {b.authors} (id {b.key.split(':')[-1]}, {b.fmt})"
                for b in matches
            )
            raise LibraryError(
                f"'{book}' matched {len(matches)} books; narrow it down or use "
                f"--book-id:\n{listing}"
            )
        return matches[0]
    raise LibraryError("Specify a book with --book, --book-id, or --file.")


# ---------------------------------------------------------------------------
# Text extraction
# ---------------------------------------------------------------------------

def _cache_path(src: Path) -> Path:
    st = src.stat()
    sig = hashlib.sha256(
        f"{src}|{st.st_size}|{int(st.st_mtime)}".encode()
    ).hexdigest()[:16]
    return cache_dir() / f"{sig}.txt"


def _clean_text(raw: str) -> str:
    """Conservative cleanup so the narration doesn't read junk aloud."""
    lines = raw.splitlines()
    out: list[str] = []
    for line in lines:
        s = line.strip()
        # Drop lines that are nothing but a page number.
        if re.fullmatch(r"\d{1,4}", s):
            continue
        # Drop common "Page 123" / "123 | Title" running headers/footers.
        if re.fullmatch(r"(?i)page\s+\d+", s):
            continue
        out.append(line.rstrip())
    text = "\n".join(out)
    # Collapse 3+ blank lines to a paragraph break; normalise odd whitespace.
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = text.replace(" ", " ")
    return text.strip()


def extract_text(book: Book, *, refresh: bool = False) -> str:
    """Return cleaned plain text for ``book``, using a disk cache."""
    cache = _cache_path(book.path)
    if cache.exists() and not refresh:
        return cache.read_text()

    if book.fmt == "txt":
        raw = book.path.read_text(errors="replace")
    else:
        ebook_convert = _require("ebook-convert")
        tmp_out = cache.with_suffix(".raw.txt")
        try:
            subprocess.run(
                [ebook_convert, str(book.path), str(tmp_out),
                 "--enable-heuristics"],
                capture_output=True, text=True, check=True,
            )
        except subprocess.CalledProcessError as e:
            raise LibraryError(
                f"ebook-convert failed on {book.path.name}: "
                f"{e.stderr.strip()[:400] or e}"
            ) from e
        raw = tmp_out.read_text(errors="replace")
        tmp_out.unlink(missing_ok=True)

    text = _clean_text(raw)
    cache.write_text(text)
    return text
