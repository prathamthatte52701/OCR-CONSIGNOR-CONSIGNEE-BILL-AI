"""Filename sanitising for anything that came from an upload and is later reused: the stored
original name, the Content-Disposition header on downloads, and entry names inside the
download-all zip. An uploaded filename (or an OCR'd invoice number used as a folder name) is
attacker-controlled text:

  - a quote / CR / LF in a Content-Disposition value corrupts or splits the header;
  - non-latin-1 characters make the header encode fail (a 500 on download);
  - "../" or an absolute path inside a zip entry is a "zip slip" when the user extracts it.

Everything is reduced to a short, ASCII-only, path-free name."""

import re

MAX_FILENAME_LENGTH = 120
_UNSAFE_CHARS = re.compile(r"[^A-Za-z0-9._() \-]")
_WHITESPACE_RUN = re.compile(r"\s+")


def safe_filename(name: str | None, fallback: str) -> str:
    """A path-free, ASCII-only version of `name`; `fallback` when nothing usable remains."""
    if not name:
        return fallback
    base = re.split(r"[\\/]", name)[-1]  # drop any directory part, either separator style
    base = _UNSAFE_CHARS.sub("_", base)
    base = _WHITESPACE_RUN.sub(" ", base).strip(" .")  # no leading/trailing dots or spaces
    base = base[:MAX_FILENAME_LENGTH].strip(" .")
    if not base or set(base) <= {"_"}:
        return fallback
    return base


def attachment_header(name: str | None, fallback: str) -> dict[str, str]:
    """Content-Disposition header for a download, with the filename made safe."""
    return {"Content-Disposition": f'attachment; filename="{safe_filename(name, fallback)}"'}
