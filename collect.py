"""
collect.py
----------
AI News Collector -- Collect Phase
AAI-501: Intro to AI and ML

Fetches articles from six AI news RSS feeds on a daily schedule.
Deduplicates by URL hash, normalizes metadata, and stores results
in a local SQLite database for downstream search and processing.

Usage:
    python collect.py

Intended to be invoked daily via cron:
    0 6 * * *   /path/to/python /path/to/collect.py
"""

import feedparser
import sqlite3
import hashlib
import uuid
import logging

from datetime import datetime, timezone
from pathlib import Path


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Path to the SQLite database file, stored in the data/ subdirectory
DB_PATH = Path(__file__).parent / "data" / "articles.db"

# Source registry: maps human-readable source names to RSS feed URLs.
# To add or remove a source, edit this dict only -- no other code changes needed.
SOURCES = {
    "IEEE Spectrum AI":  "https://spectrum.ieee.org/feeds/topic/artificial-intelligence.rss",
    "STAT News":         "https://www.statnews.com/category/health-tech/feed/",
    "The Decoder":       "https://the-decoder.com/feed/",
    "TechCrunch AI":     "https://techcrunch.com/category/artificial-intelligence/feed/",
    "Ars Technica AI":   "https://arstechnica.com/ai/feed/",
    "VentureBeat AI":    "https://venturebeat.com/category/ai/feed/",
}

# Feedparser request timeout in seconds
FETCH_TIMEOUT = 15


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

def get_connection() -> sqlite3.Connection:
    """Open a connection to the SQLite database and return it."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    # Return rows as dict-like objects accessible by column name
    conn.row_factory = sqlite3.Row
    return conn


def initialize_database(conn: sqlite3.Connection) -> None:
    """
    Create the articles and errors tables if they do not already exist.
    Safe to call on every run -- uses CREATE TABLE IF NOT EXISTS.
    """
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS articles (
            id           TEXT PRIMARY KEY,   -- UUID, stable identifier
            source       TEXT NOT NULL,      -- human-readable source name
            title        TEXT NOT NULL,
            url          TEXT NOT NULL UNIQUE,
            url_hash     TEXT NOT NULL,      -- SHA-256 of normalized URL for fast dedup
            published_at TEXT,               -- ISO 8601 UTC; NULL if feed omits date
            summary      TEXT,               -- feed-provided excerpt or abstract
            collected_at TEXT NOT NULL       -- ISO 8601 UTC timestamp of this run
        );

        CREATE TABLE IF NOT EXISTS errors (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            source       TEXT,               -- which feed caused the error (NULL if unknown)
            error_msg    TEXT,
            occurred_at  TEXT NOT NULL       -- ISO 8601 UTC
        );
    """)
    conn.commit()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def url_hash(url: str) -> str:
    """Return a SHA-256 hex digest of the lowercased, stripped URL."""
    normalized = url.strip().lower()
    return hashlib.sha256(normalized.encode()).hexdigest()


def to_utc_iso(parsed_time) -> str | None:
    """
    Convert a feedparser time struct (9-tuple) to an ISO 8601 UTC string.
    Returns None if the input is falsy or conversion fails.
    """
    if not parsed_time:
        return None
    try:
        # feedparser stores times as UTC time structs; convert via calendar
        import calendar
        ts = calendar.timegm(parsed_time)
        dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        return dt.isoformat()
    except Exception:
        return None


def now_utc_iso() -> str:
    """Return the current UTC time as an ISO 8601 string."""
    return datetime.now(tz=timezone.utc).isoformat()


def log_error(conn: sqlite3.Connection, source: str | None, message: str) -> None:
    """Insert a row into the errors table for inspection during weekly review."""
    conn.execute(
        "INSERT INTO errors (source, error_msg, occurred_at) VALUES (?, ?, ?)",
        (source, message, now_utc_iso()),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# Pipeline stages
# ---------------------------------------------------------------------------

def fetch_feed(source_name: str, feed_url: str) -> list[dict]:
    """
    Stage 1 -- Fetch.
    Parse the RSS feed at feed_url and return a list of raw entry dicts.
    Returns an empty list on any fetch or parse error.
    """
    log.info("Fetching  %s", source_name)
    try:
        # feedparser.parse() handles HTTP, redirect, encoding, and XML parsing
        feed = feedparser.parse(feed_url, request_headers={"User-Agent": "ai-news-collector/1.0"})

        # feedparser does not raise exceptions; check the bozo flag for parse errors
        if feed.bozo:
            raise ValueError(f"Feed parse warning: {feed.bozo_exception}")

        entries = []
        for entry in feed.entries:
            entries.append({
                "source":       source_name,
                "url":          entry.get("link", "").strip(),
                "title":        entry.get("title", "").strip(),
                "published_at": to_utc_iso(entry.get("published_parsed")),
                "summary":      entry.get("summary", "").strip(),
            })

        log.info("  Fetched  %d entries from %s", len(entries), source_name)
        return entries

    except Exception as exc:
        # Return empty list; caller logs to errors table
        log.warning("  Error fetching %s: %s", source_name, exc)
        return []


def deduplicate(entries: list[dict], conn: sqlite3.Connection) -> list[dict]:
    """
    Stage 2 -- Deduplicate.
    Filter out any entries whose URL hash already exists in the database.
    Also drops entries with empty URLs (malformed feed entries).
    """
    seen = set(
        row[0] for row in conn.execute("SELECT url_hash FROM articles").fetchall()
    )

    new_entries = []
    for entry in entries:
        if not entry["url"]:
            log.debug("  Skipping entry with no URL (title: %s)", entry.get("title"))
            continue
        h = url_hash(entry["url"])
        if h not in seen:
            seen.add(h)  # prevent duplicates within the same run across feeds
            entry["url_hash"] = h
            new_entries.append(entry)

    return new_entries


def normalize(entries: list[dict]) -> list[dict]:
    """
    Stage 3 -- Normalize.
    Assign a stable UUID, record collection timestamp, and ensure
    all required fields are present and consistently typed.
    """
    collected_at = now_utc_iso()
    normalized = []

    for entry in entries:
        normalized.append({
            "id":           str(uuid.uuid4()),
            "source":       entry["source"],
            "title":        entry["title"] or "(no title)",
            "url":          entry["url"],
            "url_hash":     entry["url_hash"],
            "published_at": entry.get("published_at"),   # may be None
            "summary":      entry.get("summary") or "",
            "collected_at": collected_at,
        })

    return normalized


def store(entries: list[dict], conn: sqlite3.Connection) -> int:
    """
    Stage 4 -- Store.
    Insert normalized entries into the articles table.
    Uses INSERT OR IGNORE so any race-condition duplicate is safely skipped.
    Returns the number of rows actually inserted.
    """
    inserted = 0
    for entry in entries:
        cursor = conn.execute(
            """
            INSERT OR IGNORE INTO articles
                (id, source, title, url, url_hash, published_at, summary, collected_at)
            VALUES
                (:id, :source, :title, :url, :url_hash, :published_at, :summary, :collected_at)
            """,
            entry,
        )
        inserted += cursor.rowcount
    conn.commit()
    return inserted


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    """
    Orchestrates the full collect pipeline:
        fetch -> deduplicate -> normalize -> store

    Runs once per invocation (intended to be called daily by cron).
    Errors from individual feeds are logged to the errors table and do
    not abort the run; remaining feeds are still processed.
    """
    log.info("=== Collect run started ===")
    conn = get_connection()
    initialize_database(conn)

    total_fetched   = 0
    total_new       = 0
    total_inserted  = 0

    for source_name, feed_url in SOURCES.items():
        # Stage 1: Fetch
        raw_entries = fetch_feed(source_name, feed_url)

        if not raw_entries:
            # fetch_feed already logged the warning; record to errors table
            log_error(conn, source_name, "No entries returned -- fetch may have failed")
            continue

        total_fetched += len(raw_entries)

        # Stage 2: Deduplicate
        new_entries = deduplicate(raw_entries, conn)
        log.info("  New after dedup: %d / %d", len(new_entries), len(raw_entries))
        total_new += len(new_entries)

        if not new_entries:
            continue  # nothing new from this source today

        # Stage 3: Normalize
        normalized_entries = normalize(new_entries)

        # Stage 4: Store
        inserted = store(normalized_entries, conn)
        log.info("  Stored: %d articles from %s", inserted, source_name)
        total_inserted += inserted

    conn.close()

    log.info("=== Collect run complete ===")
    log.info("    Fetched:  %d  |  New: %d  |  Inserted: %d",
             total_fetched, total_new, total_inserted)


if __name__ == "__main__":
    main()
