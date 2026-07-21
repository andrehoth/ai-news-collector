"""
search.py
---------
AI News Collector -- Search Phase

A local Flask web interface for browsing and searching collected articles.
Designed for weekly review: find, evaluate, and select articles for discussion posts.

Usage:
    python search.py

Then open http://127.0.0.1:5000 in your browser.
Press Ctrl+C to stop the server.
"""

import sqlite3
from pathlib import Path
from flask import Flask, render_template, request

app = Flask(__name__)

# Path to the SQLite database created by collect.py
DB_PATH = Path(__file__).parent / "data" / "articles.db"


def get_connection() -> sqlite3.Connection:
    """Open a read-only connection to the articles database."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # enables dict-style column access
    return conn


def get_sources() -> list[str]:
    """Return a sorted list of all source names in the database."""
    conn = get_connection()
    rows = conn.execute("SELECT DISTINCT source FROM articles ORDER BY source").fetchall()
    conn.close()
    return [row["source"] for row in rows]


@app.route("/")
def index():
    """
    Main search view.
    Accepts optional query parameters:
        q       -- keyword to search in title and summary
        source  -- filter by source name
        days    -- number of days to look back (default: 7)
    """
    # Read filter parameters from the request
    keyword = request.args.get("q", "").strip()
    source  = request.args.get("source", "").strip()
    days    = request.args.get("days", "7").strip()

    # Validate days -- fall back to 7 if not a positive integer
    try:
        days_int = max(1, int(days))
    except ValueError:
        days_int = 7

    # Build query dynamically based on active filters
    conditions = ["published_at >= date('now', :days)"]
    params = {"days": f"-{days_int} days"}

    if keyword:
        conditions.append("(title LIKE :keyword OR summary LIKE :keyword)")
        params["keyword"] = f"%{keyword}%"

    if source:
        conditions.append("source = :source")
        params["source"] = source

    where_clause = " AND ".join(conditions)

    sql = f"""
        SELECT id, source, title, url, published_at, summary
        FROM articles
        WHERE {where_clause}
        ORDER BY published_at DESC
    """

    conn = get_connection()
    articles = conn.execute(sql, params).fetchall()

    # Total article count in database for display in UI
    total_count = conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
    conn.close()

    return render_template(
        "index.html",
        articles=articles,
        sources=get_sources(),
        keyword=keyword,
        selected_source=source,
        days=str(days_int),
        result_count=len(articles),
        total_count=total_count,
    )


if __name__ == "__main__":
    if not DB_PATH.exists():
        print(f"Database not found at {DB_PATH}")
        print("Run collect.py first to populate the database.")
    else:
        print("Starting AI News search interface...")
        print("Open http://127.0.0.1:5000 in your browser")
        print("Press Ctrl+C to stop")
        app.run(debug=False)
