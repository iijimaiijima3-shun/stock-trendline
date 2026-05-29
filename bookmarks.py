"""Persistent bookmark storage using a local JSON file."""
import json
from pathlib import Path

BOOKMARK_FILE = Path(__file__).parent / "bookmarks.json"


def load_bookmarks() -> dict[str, str]:
    """Return {ticker: name} dict."""
    if BOOKMARK_FILE.exists():
        try:
            return json.loads(BOOKMARK_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_bookmarks(bookmarks: dict[str, str]) -> None:
    BOOKMARK_FILE.write_text(json.dumps(bookmarks, ensure_ascii=False, indent=2), encoding="utf-8")


def add_bookmark(ticker: str, name: str) -> None:
    bm = load_bookmarks()
    bm[ticker] = name
    save_bookmarks(bm)


def remove_bookmark(ticker: str) -> None:
    bm = load_bookmarks()
    bm.pop(ticker, None)
    save_bookmarks(bm)
